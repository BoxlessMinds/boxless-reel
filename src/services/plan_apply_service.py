"""Generic, journaled, resumable Plan/PlanOp apply executor.

This is the core engine every playlist-mutation strategy (create, dedupe,
purge, copy, add, move, reorder) plugs into: a
`Plan`'s `PlanOp` rows are executed in `sequence` order, budgeted against a
per-invocation unit ceiling, and journaled so that an interrupted run can be
resumed later without re-executing anything already `"done"`. This module
ships no concrete op type — `apply_plan` dispatches to whatever `op_type`
names an attribute on the `YouTubeDataService` instance it builds, which
keeps the engine itself free of any real YouTube-mutating logic.

Design notes:

- Step order per op is budget -> dependency -> ref-resolution -> execute
  (dependency is checked *before* ref-resolution, reversing the order the
  op-level fields are listed in the data contract) so that a `payload` ref
  pointing at the same op named by `depends_on_sequence` is never resolved
  against a `"failed"` op before the dependency check has a chance to
  cleanly `"skip"` the dependent op instead.
- A ref-placeholder resolution failure marks the op `"failed"` with
  `error_message` and halts the loop (rather than raising), matching the
  other op-level failure paths and keeping `apply_plan` exception-free for
  ordinary in-plan problems.
- `Plan.status` is never set to `"failed"` by this executor. Every halt
  path (budget, unresolved dependency, ref-resolution failure, quota
  exceeded, retries exhausted) leaves it `"applying"`, since a `"failed"`
  `PlanOp` is reset to `"pending"` at the top of the next `apply_plan` call
  — every halt is resumable, so there is no case here where the plan
  itself needs an unrecoverable terminal state.
- A dependency op that is `"failed"` or `"skipped"` cascade-skips its
  dependent op (marked `"skipped"` with an explanatory `error_message`), so
  a broken dependency chain can never leave a plan permanently halted. A
  dependency that is still `"pending"` halts the run until it resolves.
"""

import logging
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from google.oauth2.credentials import Credentials as GoogleCredentials
from sqlalchemy.orm import Session
from tenacity import (
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import settings
from src.repositories.plan_repository import PlanRepository
from src.repositories.quota_repository import QuotaRepository
from src.services.google_auth_service import GOOGLE_TOKEN_URI, get_google_auth_service
from src.services.quota_service import QuotaService
from src.services.youtube_data_service import (
    PermanentAPIError,
    QuotaExceededError,
    YouTubeDataService,
)

logger = logging.getLogger(__name__)

REF_KIND = "ref"


class PlanApplyError(Exception):
    """Base exception for genuinely exceptional `apply_plan` conditions.

    Not raised for ordinary in-plan problems (budget, dependency, quota,
    transient failures) — those are clean, non-exception halts per op-level
    or plan-level status, since a resumable executor should not force every
    caller into exception handling for expected, retryable conditions.
    """


class PlanNotFoundError(PlanApplyError):
    """Raised when `plan_id` doesn't exist, or isn't owned by `user_id`."""


def _utc_now_naive() -> datetime:
    """Current UTC time as a naive datetime (matches this repo's DateTime columns)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Anything typed as QuotaExceededError or PermanentAPIError is handled by its
# own dedicated (non-retrying) branch in the apply loop; everything else is
# treated as transient and retried with backoff before the op is marked
# "failed" and the loop halts.
_retry_apply_call = retry(
    retry=retry_if_not_exception_type((QuotaExceededError, PermanentAPIError)),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(5),
    reraise=True,
)


@_retry_apply_call
def _invoke_op(
    data_service: YouTubeDataService, op_type: str, payload: dict[str, Any]
) -> Any:
    """
    Dispatch one op's execution to `data_service`, retried if transient.

    Args:
        data_service: The `YouTubeDataService` instance to execute against.
        op_type: Name of the attribute on `data_service` to call — this
            story defines no concrete op types, so callers use whatever
            synthetic/test method the plan's ops name.
        payload: The op's ref-resolved payload, passed as keyword arguments.

    Returns:
        Whatever the dispatched call returns (must be JSON-serializable —
        it is persisted verbatim as the op's `result`). A lazily-evaluated
        iterator (e.g. `YouTubeDataService`'s existing paginated read
        methods, reused here as synthetic/test op bodies) is materialized
        into a list before returning, since it must be fully consumed for
        any `HttpError` it raises partway through to actually surface.
    Raises:
        QuotaExceededError: Never retried.
        PermanentAPIError: Never retried.
        Exception: Any other error, retried up to 5 attempts with backoff
            before propagating.
    """
    method = getattr(data_service, op_type)
    result = method(**payload)
    if isinstance(result, Iterator):
        result = list(result)
    return result


def _build_data_service(user_id: str, db: Session) -> YouTubeDataService:
    """
    Build a `YouTubeDataService` from the user's stored Google credential.

    Deliberately duplicates `PlaylistSyncService._build_data_service`'s
    small decrypt-into-locals-then-build pattern rather than reusing that
    private method cross-service — this keeps `plan_apply_service` from
    coupling to `PlaylistSyncService`'s internals.

    Args:
        user_id: The app user whose connected Google account to use.
        db: Database session.

    Returns:
        A `YouTubeDataService` client ready to execute ops.

    Raises:
        GoogleCredentialNotFoundError: If the user has no connected Google
            account.
        GoogleTokenRefreshError: If the stored access token is near/past
            expiry and refreshing it fails.
    """
    google_auth_service = get_google_auth_service(db)
    credential = google_auth_service.get_valid_credential(user_id)
    access_token = google_auth_service.repository.encryption.decrypt(
        credential.access_token
    )
    refresh_token = google_auth_service.repository.encryption.decrypt(
        credential.refresh_token
    )
    google_credentials = GoogleCredentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=GOOGLE_TOKEN_URI,
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
        scopes=credential.scopes.split(),
    )
    return YouTubeDataService(google_credentials)


def _resolve_value(
    value: Any, plan_id: str, plan_repository: PlanRepository
) -> tuple[Any, str | None]:
    """
    Resolve one payload value if it is a `{"kind": "ref", ...}` placeholder.

    Args:
        value: A literal, or a `{"kind": "ref", "ref_sequence": N}` dict.
        plan_id: ID of the owning plan.
        plan_repository: Repository used to look up the referenced op.

    Returns:
        `(resolved_value, error)` — `error` is `None` on success (including
        when `value` was already a literal, returned unchanged); otherwise
        `resolved_value` is `None` and `error` explains why resolution was
        refused.
    """
    if not (isinstance(value, dict) and value.get("kind") == REF_KIND):
        return value, None
    ref_sequence = value.get("ref_sequence")
    ref_op = plan_repository.get_op_by_sequence(plan_id, ref_sequence)
    if ref_op is None:
        return None, f"ref_sequence {ref_sequence} does not exist in plan {plan_id}"
    if ref_op.status != "done":
        return None, (
            f"ref_sequence {ref_sequence} has status {ref_op.status!r}, not "
            "'done' -- refusing to resolve from an untrustworthy result"
        )
    return ref_op.result, None


def _resolve_payload(
    payload: dict[str, Any] | None, plan_id: str, plan_repository: PlanRepository
) -> tuple[dict[str, Any], str | None]:
    """
    Resolve every top-level ref placeholder in an op's payload.

    Args:
        payload: The op's raw payload (may be `None`).
        plan_id: ID of the owning plan.
        plan_repository: Repository used to look up referenced ops.

    Returns:
        `(resolved_payload, error)` — on the first unresolved ref, resolution
        stops immediately and `error` is set; `resolved_payload` is `{}` in
        that case.
    """
    resolved: dict[str, Any] = {}
    for key, value in (payload or {}).items():
        resolved_value, error = _resolve_value(value, plan_id, plan_repository)
        if error is not None:
            return {}, error
        resolved[key] = resolved_value
    return resolved, None


def apply_plan(plan_id: str, user_id: str, budget_units: int, db: Session) -> None:
    """
    Apply a plan's pending ops in sequence order, resumably and budgeted.

    Leaves correct committed database state for the caller to re-read via
    `PlanRepository` — this function returns nothing. A halt (budget
    exhausted, unresolved dependency, quota exceeded, or a failed op after
    retries) is a clean early return, not an exception: `Plan.status` stays
    `"applying"` so a later call to `apply_plan` with the same `plan_id`
    resumes correctly, executing no op twice.

    Args:
        plan_id: ID of the plan to apply.
        user_id: The app user invoking apply — must own the plan; also the
            attribution on every `QuotaLedgerEntry` this run writes.
        budget_units: Ceiling on units this single invocation may spend
            (distinct from `Plan.budget_units`, the plan's overall ceiling).
        db: Database session.

    Raises:
        PlanNotFoundError: If no plan with `plan_id` exists for `user_id`.
    """
    plan_repository = PlanRepository(db)
    quota_repository = QuotaRepository(db)
    quota_service = QuotaService(quota_repository)

    plan = plan_repository.get_by_id(plan_id, user_id=user_id)
    if plan is None:
        raise PlanNotFoundError(f"Plan {plan_id} not found for user {user_id}")

    if plan.status != "applying":
        plan_repository.update_plan_status(plan_id, "applying")

    all_ops = plan_repository.get_ops_for_plan(plan_id)

    # A "failed" op is normally retried on the next run -- reset it to
    # "pending" -- *unless* some other still-pending op's
    # `depends_on_sequence` is waiting on it. Resetting unconditionally
    # would make the dependency check's "dependency failed -> skip this
    # op" branch below unreachable, since the failed op would always have
    # flipped back to "pending" (-> "unresolved, halt") before any
    # dependent op could ever observe it as "failed". Once a dependent has
    # actually been skipped for this reason (a terminal state), nothing
    # further depends on the failed op's fate, so a later call is free to
    # reset and retry it like any other failed op.
    pending_dependents_of = {
        op.depends_on_sequence
        for op in all_ops
        if op.status == "pending" and op.depends_on_sequence is not None
    }
    for stale_op in plan_repository.get_ops_by_status(plan_id, statuses=["failed"]):
        if stale_op.sequence not in pending_dependents_of:
            plan_repository.update_op_status(stale_op.id, "pending")

    total_spent = sum(
        op.actual_units or 0 for op in all_ops if op.status == "done"
    )

    data_service: YouTubeDataService | None = None

    for op in plan_repository.get_ops_by_status(plan_id, statuses=["pending"]):
        if total_spent + op.estimated_units > budget_units:
            logger.info(
                "Plan %s halting at op %d: budget %d units would be exceeded",
                plan_id, op.sequence, budget_units,
            )
            return

        if op.depends_on_sequence is not None:
            dependency = plan_repository.get_op_by_sequence(
                plan_id, op.depends_on_sequence
            )
            if dependency is None or dependency.status not in (
                "done", "failed", "skipped",
            ):
                logger.info(
                    "Plan %s halting at op %d: dependency op %s not yet resolved",
                    plan_id, op.sequence, op.depends_on_sequence,
                )
                return
            if dependency.status in ("failed", "skipped"):
                plan_repository.update_op_status(
                    op.id,
                    "skipped",
                    error_message=(
                        f"dependency op {op.depends_on_sequence} {dependency.status}"
                    ),
                    executed_at=_utc_now_naive(),
                )
                continue

        resolved_payload, ref_error = _resolve_payload(
            op.payload, plan_id, plan_repository
        )
        if ref_error is not None:
            plan_repository.update_op_status(
                op.id, "failed", error_message=ref_error, executed_at=_utc_now_naive()
            )
            logger.error(
                "Plan %s halting at op %d: %s", plan_id, op.sequence, ref_error
            )
            return

        if data_service is None:
            data_service = _build_data_service(user_id, db)

        try:
            result = _invoke_op(data_service, op.op_type, resolved_payload)
        except QuotaExceededError:
            logger.warning(
                "Plan %s halting at op %d: quota exceeded", plan_id, op.sequence
            )
            return
        except PermanentAPIError as e:
            logger.warning(
                "Plan %s op %d skipped: permanent API error: %s",
                plan_id, op.sequence, e,
            )
            plan_repository.update_op_status(
                op.id, "skipped", error_message=str(e), executed_at=_utc_now_naive()
            )
            continue
        except Exception as e:
            logger.exception(
                "Plan %s halting at op %d: failed after retries", plan_id, op.sequence
            )
            plan_repository.update_op_status(
                op.id, "failed", error_message=str(e), executed_at=_utc_now_naive()
            )
            return

        actual_units = op.estimated_units
        plan_repository.update_op_status(
            op.id,
            "done",
            result=result,
            actual_units=actual_units,
            executed_at=_utc_now_naive(),
        )
        quota_service.record_read(user_id, endpoint=op.op_type, units=actual_units)
        total_spent += actual_units

    # The loop only reaches here after processing every op that was
    # "pending" at its start without an early-return halt, so every op is
    # now terminal ("done" or "skipped") -- the plan is fully applied.
    plan_repository.update_plan_status(plan_id, "done")
