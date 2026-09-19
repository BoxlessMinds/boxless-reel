"""Tests for the Plan/Apply executor.

No test here ever reaches the network or spends real YouTube Data API
quota. Two mocking strategies are used, deliberately:

- Most tests patch `src.services.plan_apply_service.YouTubeDataService`
  with a plain `MagicMock` stand-in (the same pattern already established
  in `tests/test_playlist_sync_service.py`) — these exercise the
  executor's own orchestration (resume, budget, dependency, ref
  resolution), which is independent of HTTP-error classification.
- `TestQuotaExceeded` (AC3) uses the *real* `YouTubeDataService` class with
  only `googleapiclient.discovery.build` mocked (the pattern from
  `tests/test_youtube_data_service.py`), so the highest-risk path — a real
  403 quotaExceeded `HttpError` being classified and halting the loop
  without retry — is proven end to end rather than assumed.

Google OAuth is always mocked via a stand-in for `GoogleAuthService` (never
touches real OAuth endpoints or a real encrypted credential).
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httplib2
import pytest
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session

from src.models.playlist import QuotaLedgerEntry
from src.models.plan import Plan, PlanOp
from src.models.user import User
from src.repositories.plan_repository import PlanRepository
from src.services.plan_apply_service import (
    PlanNotFoundError,
    _invoke_op,
    _resolve_payload,
    _resolve_value,
    apply_plan,
)
from src.services.youtube_data_service import PermanentAPIError, QuotaExceededError


def _http_error(status: int, reason: str, message: str = "error") -> HttpError:
    """Build a real googleapiclient HttpError with a Google-shaped error body."""
    content = json.dumps(
        {"error": {"errors": [{"reason": reason, "message": message}], "code": status}}
    ).encode("utf-8")
    return HttpError(httplib2.Response({"status": status}), content)


def _make_plan(db: Session, user_id: str, kind: str = "test_kind") -> Plan:
    """Persist a bare Plan row directly (no apply_plan involvement)."""
    return PlanRepository(db).create_plan(Plan(user_id=user_id, kind=kind))


def _make_op(
    db: Session,
    plan_id: str,
    sequence: int,
    op_type: str = "noop",
    payload: dict | None = None,
    estimated_units: int = 1,
    depends_on_sequence: int | None = None,
    status: str = "pending",
    result: dict | None = None,
) -> PlanOp:
    """Persist a bare PlanOp row directly (no apply_plan involvement)."""
    op = PlanOp(
        plan_id=plan_id,
        sequence=sequence,
        op_type=op_type,
        payload=payload,
        estimated_units=estimated_units,
        depends_on_sequence=depends_on_sequence,
        status=status,
        result=result,
    )
    return PlanRepository(db).create_ops([op])[0]


@pytest.fixture
def fake_credential() -> SimpleNamespace:
    """A fake GoogleOAuthCredential-shaped object with ciphertext tokens."""
    return SimpleNamespace(
        access_token="ciphertext-access",
        refresh_token="ciphertext-refresh",
        scopes="https://www.googleapis.com/auth/youtube",
    )


@pytest.fixture
def mock_google_auth_service(fake_credential: SimpleNamespace):
    """Patch `get_google_auth_service` so no test touches real Google OAuth."""
    service = MagicMock()
    service.get_valid_credential.return_value = fake_credential
    service.repository.encryption.decrypt.side_effect = lambda value: f"decrypted:{value}"
    with patch(
        "src.services.plan_apply_service.get_google_auth_service", return_value=service
    ):
        yield service


class TestPlanCreationIsFree:
    """AC1: creating a Plan/PlanOp never touches the API or the quota ledger."""

    def test_plan_creation_is_free(self, test_db: Session, test_user: User) -> None:
        with patch("src.services.youtube_data_service.build") as mock_build:
            plan = _make_plan(test_db, test_user.id)
            _make_op(test_db, plan.id, sequence=0)
            _make_op(test_db, plan.id, sequence=1)

        assert mock_build.call_count == 0
        assert test_db.query(QuotaLedgerEntry).count() == 0
        assert plan.status == "pending"


class TestResume:
    """AC2: an interrupted apply_plan run resumes without re-executing any op."""

    def test_resume_executes_each_op_exactly_once_across_two_calls(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        plan = _make_plan(test_db, test_user.id)
        for i in range(3):
            _make_op(
                test_db, plan.id, sequence=i, op_type=f"synthetic_op_{i}",
                estimated_units=100,
            )

        mock_data_service = MagicMock()
        for i in range(3):
            getattr(mock_data_service, f"synthetic_op_{i}").return_value = {"n": i}

        plan_repository = PlanRepository(test_db)

        # Budget only covers op0 -- the loop must halt cleanly before ever
        # invoking op1's or op2's mock (this simulates "aborts partway
        # through" without relying on retry timing, so per-op call counts
        # stay exact).
        with patch(
            "src.services.plan_apply_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            apply_plan(plan.id, test_user.id, budget_units=100, db=test_db)

        statuses = [op.status for op in plan_repository.get_ops_for_plan(plan.id)]
        assert statuses == ["done", "pending", "pending"]
        assert mock_data_service.synthetic_op_0.call_count == 1
        assert mock_data_service.synthetic_op_1.call_count == 0
        assert mock_data_service.synthetic_op_2.call_count == 0
        assert plan_repository.get_by_id(plan.id).status == "applying"

        with patch(
            "src.services.plan_apply_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            apply_plan(plan.id, test_user.id, budget_units=1000, db=test_db)

        statuses = [op.status for op in plan_repository.get_ops_for_plan(plan.id)]
        assert statuses == ["done", "done", "done"]
        assert mock_data_service.synthetic_op_0.call_count == 1
        assert mock_data_service.synthetic_op_1.call_count == 1
        assert mock_data_service.synthetic_op_2.call_count == 1
        assert not any(status == "pending" for status in statuses)
        assert plan_repository.get_by_id(plan.id).status == "done"

    def test_apply_plan_raises_for_unknown_plan(
        self, test_db: Session, test_user: User
    ) -> None:
        with pytest.raises(PlanNotFoundError):
            apply_plan("does-not-exist", test_user.id, budget_units=100, db=test_db)

    def test_apply_plan_raises_when_not_owned_by_user(
        self, test_db: Session, test_user: User, test_admin: User
    ) -> None:
        plan = _make_plan(test_db, test_user.id)
        with pytest.raises(PlanNotFoundError):
            apply_plan(plan.id, test_admin.id, budget_units=100, db=test_db)


class TestQuotaExceeded:
    """AC3: a real 403 quotaExceeded halts the loop cleanly, no retry, resumable."""

    def test_quota_exceeded_halts_without_retry_and_resumes(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        plan = _make_plan(test_db, test_user.id)
        for i in range(3):
            _make_op(test_db, plan.id, sequence=i, op_type="list_my_playlists")

        plan_repository = PlanRepository(test_db)

        with patch("src.services.youtube_data_service.build") as mock_build:
            mock_client = MagicMock()
            mock_build.return_value = mock_client
            mock_client.playlists.return_value.list.return_value.execute.side_effect = [
                {"items": [{"id": "PL-op0"}]},  # op0 succeeds
                _http_error(403, "quotaExceeded"),  # op1 halts, no retry
            ]

            apply_plan(plan.id, test_user.id, budget_units=10_000, db=test_db)

            assert (
                mock_client.playlists.return_value.list.return_value.execute.call_count
                == 2
            )

        statuses = {op.sequence: op.status for op in plan_repository.get_ops_for_plan(plan.id)}
        assert statuses == {0: "done", 1: "pending", 2: "pending"}
        assert plan_repository.get_by_id(plan.id).status == "applying"
        assert test_db.query(QuotaLedgerEntry).count() == 1

        with patch("src.services.youtube_data_service.build") as mock_build:
            mock_client = MagicMock()
            mock_build.return_value = mock_client
            mock_client.playlists.return_value.list.return_value.execute.side_effect = [
                {"items": [{"id": "PL-op1"}]},
                {"items": [{"id": "PL-op2"}]},
            ]

            apply_plan(plan.id, test_user.id, budget_units=10_000, db=test_db)

        statuses = {op.sequence: op.status for op in plan_repository.get_ops_for_plan(plan.id)}
        assert statuses == {0: "done", 1: "done", 2: "done"}
        assert plan_repository.get_by_id(plan.id).status == "done"
        assert test_db.query(QuotaLedgerEntry).count() == 3


class TestTenacityExcludesQuotaExceeded:
    """CRITICAL: tenacity must never retry a QuotaExceededError."""

    def test_invoke_op_does_not_retry_quota_exceeded(self) -> None:
        mock_data_service = MagicMock()
        mock_data_service.some_op.side_effect = QuotaExceededError("quota gone")

        with pytest.raises(QuotaExceededError):
            _invoke_op(mock_data_service, "some_op", {})

        assert mock_data_service.some_op.call_count == 1

    def test_invoke_op_does_not_retry_permanent_api_error(self) -> None:
        mock_data_service = MagicMock()
        mock_data_service.some_op.side_effect = PermanentAPIError("not found")

        with pytest.raises(PermanentAPIError):
            _invoke_op(mock_data_service, "some_op", {})

        assert mock_data_service.some_op.call_count == 1

    def test_invoke_op_retries_other_errors(self) -> None:
        mock_data_service = MagicMock()
        mock_data_service.some_op.side_effect = [RuntimeError("transient"), {"ok": True}]

        with patch("time.sleep"):
            result = _invoke_op(mock_data_service, "some_op", {})

        assert result == {"ok": True}
        assert mock_data_service.some_op.call_count == 2


class TestPermanentAPIError:
    """Other 4xx: skip just the offending op, continue the loop (no halt)."""

    def test_permanent_error_skips_op_and_continues(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        plan = _make_plan(test_db, test_user.id)
        _make_op(test_db, plan.id, sequence=0, op_type="op_a")
        _make_op(test_db, plan.id, sequence=1, op_type="op_b")

        mock_data_service = MagicMock()
        mock_data_service.op_a.side_effect = PermanentAPIError("item already gone")
        mock_data_service.op_b.return_value = {"ok": True}

        with patch(
            "src.services.plan_apply_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            apply_plan(plan.id, test_user.id, budget_units=1000, db=test_db)

        plan_repository = PlanRepository(test_db)
        ops = {op.sequence: op for op in plan_repository.get_ops_for_plan(plan.id)}
        assert ops[0].status == "skipped"
        assert ops[0].error_message == "item already gone"
        assert ops[1].status == "done"
        assert plan_repository.get_by_id(plan.id).status == "done"


class TestTransientRetriesExhausted:
    """Retries exhausted: mark the op failed, halt, and retry it on the next call."""

    def test_op_marked_failed_and_reset_to_pending_on_next_call(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        plan = _make_plan(test_db, test_user.id)
        _make_op(test_db, plan.id, sequence=0, op_type="flaky_op")
        _make_op(test_db, plan.id, sequence=1, op_type="op_after")

        mock_data_service = MagicMock()
        mock_data_service.flaky_op.side_effect = RuntimeError("still broken")
        mock_data_service.op_after.return_value = {"ok": True}

        plan_repository = PlanRepository(test_db)

        with patch(
            "src.services.plan_apply_service.YouTubeDataService",
            return_value=mock_data_service,
        ), patch("time.sleep"):
            apply_plan(plan.id, test_user.id, budget_units=1000, db=test_db)

        ops = {op.sequence: op for op in plan_repository.get_ops_for_plan(plan.id)}
        assert ops[0].status == "failed"
        assert ops[0].error_message == "still broken"
        assert ops[1].status == "pending"  # never reached -- loop halted
        assert plan_repository.get_by_id(plan.id).status == "applying"
        assert mock_data_service.flaky_op.call_count == 5  # stop_after_attempt(5)

        # Next call: the failed op is reset to pending and retried.
        mock_data_service.flaky_op.side_effect = None
        mock_data_service.flaky_op.return_value = {"ok": True}

        with patch(
            "src.services.plan_apply_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            apply_plan(plan.id, test_user.id, budget_units=1000, db=test_db)

        ops = {op.sequence: op for op in plan_repository.get_ops_for_plan(plan.id)}
        assert ops[0].status == "done"
        assert ops[1].status == "done"
        assert plan_repository.get_by_id(plan.id).status == "done"


class TestDependency:
    """depends_on_sequence gating: skip-on-failed-dependency, halt-on-unresolved."""

    def test_skips_when_dependency_failed(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        plan = _make_plan(test_db, test_user.id)
        _make_op(test_db, plan.id, sequence=0, op_type="dep_op", status="failed")
        _make_op(
            test_db, plan.id, sequence=1, op_type="dependent_op", depends_on_sequence=0
        )

        mock_data_service = MagicMock()

        plan_repository = PlanRepository(test_db)
        with patch(
            "src.services.plan_apply_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            apply_plan(plan.id, test_user.id, budget_units=1000, db=test_db)

        ops = {op.sequence: op for op in plan_repository.get_ops_for_plan(plan.id)}
        # dep_op is pre-seeded "failed" and has a still-pending dependent,
        # so it is *not* auto-reset to "pending" this run -- letting the
        # dependent see it as "failed" and cascade a clean "skipped"
        # instead of re-attempting dep_op.
        assert ops[0].status == "failed"
        assert ops[1].status == "skipped"
        assert ops[1].error_message == "dependency op 0 failed"
        mock_data_service.dep_op.assert_not_called()
        mock_data_service.dependent_op.assert_not_called()
        assert plan_repository.get_by_id(plan.id).status == "done"

    def test_failed_dependency_is_retried_once_dependent_already_skipped(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        """A failed op with no remaining pending dependents is retried normally."""
        plan = _make_plan(test_db, test_user.id)
        _make_op(test_db, plan.id, sequence=0, op_type="dep_op", status="failed")
        _make_op(
            test_db, plan.id, sequence=1, op_type="dependent_op",
            depends_on_sequence=0, status="skipped",
        )

        mock_data_service = MagicMock()
        mock_data_service.dep_op.return_value = {"ok": True}

        plan_repository = PlanRepository(test_db)
        with patch(
            "src.services.plan_apply_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            apply_plan(plan.id, test_user.id, budget_units=1000, db=test_db)

        ops = {op.sequence: op for op in plan_repository.get_ops_for_plan(plan.id)}
        assert ops[0].status == "done"
        assert ops[1].status == "skipped"  # untouched -- already terminal
        mock_data_service.dep_op.assert_called_once()

    def test_halts_when_dependency_still_pending(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        plan = _make_plan(test_db, test_user.id)
        # dependent_op (sequence 0) depends on an op that hasn't run yet
        # (sequence 1, still pending) -- processed first by sequence order.
        _make_op(
            test_db, plan.id, sequence=0, op_type="dependent_op", depends_on_sequence=1
        )
        _make_op(test_db, plan.id, sequence=1, op_type="dep_op")

        mock_data_service = MagicMock()

        plan_repository = PlanRepository(test_db)
        with patch(
            "src.services.plan_apply_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            apply_plan(plan.id, test_user.id, budget_units=1000, db=test_db)

        ops = {op.sequence: op for op in plan_repository.get_ops_for_plan(plan.id)}
        assert ops[0].status == "pending"
        assert ops[1].status == "pending"
        mock_data_service.dependent_op.assert_not_called()
        mock_data_service.dep_op.assert_not_called()
        assert plan_repository.get_by_id(plan.id).status == "applying"

    def test_dependency_done_allows_dependent_to_proceed_after_interruption(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        """A move's insert (sequence 0) completes, the run
        halts on budget before the paired delete (sequence 1,
        `depends_on_sequence=0`) executes, and resuming later lets the
        delete proceed once it observes a "done" dependency -- the video is
        never lost (delete never ran while absent from the target) and
        never duplicated (delete does run once the insert is confirmed).
        """
        plan = _make_plan(test_db, test_user.id)
        _make_op(test_db, plan.id, sequence=0, op_type="insert_op", estimated_units=100)
        _make_op(
            test_db, plan.id, sequence=1, op_type="delete_op",
            depends_on_sequence=0, estimated_units=100,
        )

        mock_data_service = MagicMock()
        mock_data_service.insert_op.return_value = {"id": "item-1"}
        mock_data_service.delete_op.return_value = {"deleted": True}

        plan_repository = PlanRepository(test_db)

        with patch(
            "src.services.plan_apply_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            # Budget only covers op0 -- op1 must not run this call.
            apply_plan(plan.id, test_user.id, budget_units=100, db=test_db)

        ops = {op.sequence: op for op in plan_repository.get_ops_for_plan(plan.id)}
        assert ops[0].status == "done"
        assert ops[1].status == "pending"
        mock_data_service.delete_op.assert_not_called()
        assert plan_repository.get_by_id(plan.id).status == "applying"

        with patch(
            "src.services.plan_apply_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            apply_plan(plan.id, test_user.id, budget_units=1000, db=test_db)

        ops = {op.sequence: op for op in plan_repository.get_ops_for_plan(plan.id)}
        assert ops[0].status == "done"
        assert ops[1].status == "done"
        mock_data_service.delete_op.assert_called_once()
        assert plan_repository.get_by_id(plan.id).status == "done"


class TestSkippedDependencyCascades:
    """A "skipped" dependency now cascade-skips its dependent,
    same as a "failed" one.

    Regression test: the dependency check used to treat "skipped" exactly
    like "pending" (an unresolved halt), rather than cascading like
    "failed" does -- a dependency lands on "skipped" (never
    "failed") when it hits `PermanentAPIError` (see the branch a few dozen
    lines up in `apply_plan`), e.g. a move's insert-into-target failing
    because the target playlist vanished mid-move. Since nothing in this
    module ever transitions a "skipped" op's status again, the paired
    delete would halt identically on every future `apply_plan` call
    forever -- the video was never lost (the delete never ran), but the
    plan could never reach `status="done"` again. The fix extends the
    resolved-status set and the cascade-skip condition to include
    "skipped".
    """

    def test_skipped_dependency_cascades_and_plan_reaches_done(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        plan = _make_plan(test_db, test_user.id)
        _make_op(test_db, plan.id, sequence=0, op_type="insert_op")
        _make_op(
            test_db, plan.id, sequence=1, op_type="delete_op", depends_on_sequence=0
        )

        mock_data_service = MagicMock()
        mock_data_service.insert_op.side_effect = PermanentAPIError(
            "target playlist vanished"
        )

        plan_repository = PlanRepository(test_db)

        with patch(
            "src.services.plan_apply_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            apply_plan(plan.id, test_user.id, budget_units=1000, db=test_db)

        ops = {op.sequence: op for op in plan_repository.get_ops_for_plan(plan.id)}
        assert ops[0].status == "skipped"  # insert permanently failed
        assert ops[1].status == "skipped"  # cascaded -- delete never executed
        assert ops[1].error_message == "dependency op 0 skipped"
        mock_data_service.delete_op.assert_not_called()  # video safe in source
        # The plan reaches a terminal state instead of deadlocking forever.
        assert plan_repository.get_by_id(plan.id).status == "done"


class TestRefResolution:
    """AC4: {"kind":"ref","ref_sequence":N} resolves only from a done op's result."""

    def test_ref_resolves_from_done_op_result(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        plan = _make_plan(test_db, test_user.id)
        _make_op(test_db, plan.id, sequence=0, op_type="produce")
        _make_op(
            test_db, plan.id, sequence=1, op_type="consume",
            payload={"target": {"kind": "ref", "ref_sequence": 0}},
        )

        mock_data_service = MagicMock()
        mock_data_service.produce.return_value = {"id": "op0-result"}
        mock_data_service.consume.return_value = {"ok": True}

        with patch(
            "src.services.plan_apply_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            apply_plan(plan.id, test_user.id, budget_units=1000, db=test_db)

        mock_data_service.consume.assert_called_once_with(target={"id": "op0-result"})
        plan_repository = PlanRepository(test_db)
        ops = {op.sequence: op for op in plan_repository.get_ops_for_plan(plan.id)}
        assert ops[0].status == "done"
        assert ops[1].status == "done"
        assert ops[1].result == {"ok": True}

    def test_ref_to_still_pending_op_refuses_and_halts(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        plan = _make_plan(test_db, test_user.id)
        # Sequence 0 references sequence 5's result -- 5 hasn't run yet
        # (still "pending") when 0 is processed.
        _make_op(
            test_db, plan.id, sequence=0, op_type="consume",
            payload={"target": {"kind": "ref", "ref_sequence": 5}},
        )
        _make_op(test_db, plan.id, sequence=5, op_type="produce")

        mock_data_service = MagicMock()
        mock_data_service.produce.return_value = {"id": "should-not-be-used"}

        plan_repository = PlanRepository(test_db)
        with patch(
            "src.services.plan_apply_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            apply_plan(plan.id, test_user.id, budget_units=1000, db=test_db)

        ops = {op.sequence: op for op in plan_repository.get_ops_for_plan(plan.id)}
        assert ops[0].status == "failed"
        assert "pending" in ops[0].error_message
        assert ops[5].status == "pending"  # never reached -- loop halted
        mock_data_service.produce.assert_not_called()
        mock_data_service.consume.assert_not_called()
        assert plan_repository.get_by_id(plan.id).status == "applying"

    def test_resolve_value_refuses_pending_and_failed_ops(
        self, test_db: Session, test_user: User
    ) -> None:
        plan = _make_plan(test_db, test_user.id)
        pending_op = _make_op(test_db, plan.id, sequence=0, status="pending")
        failed_op = _make_op(test_db, plan.id, sequence=1, status="failed")
        done_op = _make_op(
            test_db, plan.id, sequence=2, status="done", result={"value": 42}
        )
        plan_repository = PlanRepository(test_db)

        for op in (pending_op, failed_op):
            value, error = _resolve_value(
                {"kind": "ref", "ref_sequence": op.sequence}, plan.id, plan_repository
            )
            assert value is None
            assert error is not None and op.status in error

        value, error = _resolve_value(
            {"kind": "ref", "ref_sequence": done_op.sequence}, plan.id, plan_repository
        )
        assert error is None
        assert value == {"value": 42}

    def test_resolve_payload_passes_literals_through_unchanged(
        self, test_db: Session, test_user: User
    ) -> None:
        plan = _make_plan(test_db, test_user.id)
        plan_repository = PlanRepository(test_db)

        resolved, error = _resolve_payload(
            {"video_id": "dQw4w9WgXcQ", "count": 3}, plan.id, plan_repository
        )

        assert error is None
        assert resolved == {"video_id": "dQw4w9WgXcQ", "count": 3}
