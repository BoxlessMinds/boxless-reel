"""API routes for the plan/apply execution engine."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.config import settings
from src.database import get_db
from src.dependencies.auth import CurrentUser
from src.models.plan import Plan, PlanOp
from src.repositories.plan_repository import PlanRepository
from src.schemas.plan import (
    ApplyPlanRequest,
    CreatePlanRequest,
    PlanOpResponse,
    PlanResponse,
)
from src.services.exceptions import InvalidVideoIdError
from src.services.google_auth_service import (
    GoogleAuthServiceError,
    GoogleCredentialNotFoundError,
    GoogleTokenRefreshError,
)
from src.services.plan_apply_service import apply_plan
from src.services.playlist_planning_service import (
    PlaylistPlanningService,
    get_playlist_planning_service,
)
from src.services.youtube_data_service import QuotaExceededError, YouTubeDataServiceError

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_plan_repository(db: Session = Depends(get_db)) -> PlanRepository:
    """Dependency that provides a PlanRepository instance."""
    return PlanRepository(db)


def _get_planning_service(db: Session = Depends(get_db)) -> PlaylistPlanningService:
    """Dependency that provides a PlaylistPlanningService instance."""
    return get_playlist_planning_service(db)


def _to_plan_response(plan: Plan, ops: list[PlanOp]) -> PlanResponse:
    """Serialize a plan and its ops into a PlanResponse, with unit rollups.

    Args:
        plan: The plan to serialize.
        ops: The plan's ops, ordered by sequence.

    Returns:
        A PlanResponse including total_estimated_units/total_actual_units
        computed here (not on the schema) from the ops just fetched.
    """
    total_estimated_units = sum(op.estimated_units for op in ops)
    total_actual_units = sum(op.actual_units or 0 for op in ops)
    return PlanResponse(
        id=plan.id,
        user_id=plan.user_id,
        kind=plan.kind,
        status=plan.status,
        params=plan.params,
        budget_units=plan.budget_units,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        ops=[PlanOpResponse.model_validate(op) for op in ops],
        total_estimated_units=total_estimated_units,
        total_actual_units=total_actual_units,
    )


@router.post("", response_model=PlanResponse, status_code=201)
async def create_plan(
    request: CreatePlanRequest,
    current_user: CurrentUser,
    planning_service: PlaylistPlanningService = Depends(_get_planning_service),
    repository: PlanRepository = Depends(_get_plan_repository),
) -> PlanResponse:
    """
    Generate a new plan for review (dry-run) -- never executes anything.

    `kind="dedupe"` and `kind="purge_unavailable"` (mode="deleted", the
    default) never call the YouTube Data API to generate their plan --
    only `kind="purge_unavailable"` with `enrich=True` (or
    `mode="deleted_and_private"`, which forces it) makes one read call
    (`videos.list`) as part of generating the plan itself.

    Args:
        request: Plan-generation request -- kind="create"/"dedupe"/
            "purge_unavailable"/"copy"/"add_url"/"purge_watched"/"move"/
            "reorder".
        current_user: Authenticated user.
        planning_service: Injected PlaylistPlanningService instance.
        repository: Injected PlanRepository instance.

    Returns:
        The newly created plan, with status "pending" and its ops populated
        for review via this same response (or a later GET /plans/{id}).

    Raises:
        HTTPException: 404 if a dedupe/purge_unavailable/copy/add_url/
            purge_watched/move/reorder's playlist(s) do not exist or are
            not owned by the current user; 400 if an add_url URL/ID is
            malformed; 400/401/429/502 if a purge's enrichment pass, or a
            copy's (or add_url's list= expansion's) on-demand source
            caching, fails (no connected Google account, expired
            credentials, exhausted quota, or another API error,
            respectively).
    """
    try:
        if request.kind == "create":
            plan = planning_service.plan_create(
                user_id=current_user.id,
                title=request.title,
                description=request.description,
                privacy_status=request.privacy_status,
            )
        elif request.kind == "dedupe":
            plan = planning_service.plan_dedupe(
                user_id=current_user.id, playlist_id=request.playlist_id
            )
        elif request.kind == "purge_unavailable":
            plan = planning_service.plan_purge_unavailable(
                user_id=current_user.id,
                playlist_id=request.playlist_id,
                mode=request.mode,
                enrich=request.enrich,
            )
        elif request.kind == "copy":
            plan = planning_service.plan_copy(
                user_id=current_user.id,
                source_playlist_ids=request.source_playlist_ids,
                target_playlist_id=request.target_playlist_id,
                target_title=request.target_title,
                filter_regex=request.filter_regex,
                force_new=request.force_new,
            )
        elif request.kind == "add_url":
            plan = planning_service.plan_add_urls(
                user_id=current_user.id,
                urls=request.urls,
                target_playlist_id=request.target_playlist_id,
                target_title=request.target_title,
            )
        elif request.kind == "purge_watched":
            plan = planning_service.plan_purge_watched(
                user_id=current_user.id,
                playlist_id=request.playlist_id,
                watched_before=request.watched_before,
            )
        elif request.kind == "move":
            plan = planning_service.plan_move(
                user_id=current_user.id,
                source_playlist_id=request.source_playlist_id,
                target_playlist_id=request.target_playlist_id,
                filter_regex=request.filter_regex,
            )
        else:
            plan = planning_service.plan_reorder(
                user_id=current_user.id,
                playlist_id=request.playlist_id,
                sort_by=request.sort_by,
            )
    except InvalidVideoIdError as e:
        logger.warning(
            "Plan generation rejected a malformed URL/ID (user=%s): %s",
            current_user.id, e,
        )
        raise HTTPException(status_code=400, detail=str(e))
    except GoogleCredentialNotFoundError as e:
        logger.warning(
            "Plan generation attempted with no connected Google account (user=%s): %s",
            current_user.id, e,
        )
        raise HTTPException(status_code=400, detail=str(e))
    except GoogleTokenRefreshError as e:
        logger.warning(
            "Plan generation failed - could not refresh Google credentials (user=%s): %s",
            current_user.id, e,
        )
        raise HTTPException(status_code=401, detail=str(e))
    except GoogleAuthServiceError as e:
        logger.error("Plan generation failed - Google auth service error (user=%s): %s", current_user.id, e)
        raise HTTPException(status_code=502, detail=str(e))
    except QuotaExceededError as e:
        logger.error("Plan generation failed - YouTube Data API quota exhausted (user=%s): %s", current_user.id, e)
        raise HTTPException(status_code=429, detail=str(e))
    except YouTubeDataServiceError as e:
        logger.error("Plan generation failed - YouTube Data API error (user=%s): %s", current_user.id, e)
        raise HTTPException(status_code=502, detail=str(e))

    if plan is None:
        if request.kind == "copy":
            detail = (
                f"Target or source playlist not found for copy "
                f"(sources={request.source_playlist_ids})"
            )
        elif request.kind == "add_url":
            detail = (
                f"Target or source playlist not found for add_url "
                f"(target_playlist_id={request.target_playlist_id})"
            )
        elif request.kind == "move":
            detail = (
                f"Source or target playlist not found for move "
                f"(source={request.source_playlist_id}, target={request.target_playlist_id})"
            )
        else:
            detail = f"Playlist not found: {request.playlist_id}"
        raise HTTPException(status_code=404, detail=detail)

    ops = repository.get_ops_for_plan(plan.id)
    return _to_plan_response(plan, ops)


@router.get("/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: str,
    current_user: CurrentUser,
    repository: PlanRepository = Depends(_get_plan_repository),
) -> PlanResponse:
    """
    Get a plan and its ordered ops, with quota unit rollups.

    Args:
        plan_id: UUID of the plan.
        current_user: Authenticated user.
        repository: Injected PlanRepository instance.

    Returns:
        The plan's current persisted state.

    Raises:
        HTTPException: 404 if the plan does not exist or is not owned by
            the current user.
    """
    plan = repository.get_by_id(plan_id, user_id=current_user.id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Plan not found: {plan_id}")

    ops = repository.get_ops_for_plan(plan_id)
    return _to_plan_response(plan, ops)


@router.post("/{plan_id}/apply", response_model=PlanResponse)
async def apply_plan_endpoint(
    plan_id: str,
    current_user: CurrentUser,
    request: ApplyPlanRequest,
    repository: PlanRepository = Depends(_get_plan_repository),
    db: Session = Depends(get_db),
) -> PlanResponse:
    """
    Apply a plan: execute its pending ops in sequence order, up to budget.

    A 403 quota-exceeded halt is a normal, non-exception return from the
    executor — the plan is left "applying" and this endpoint always
    re-fetches and returns whatever state actually got committed, never
    trusting the executor's raw return value (this is what "resumable"
    means at the API layer).

    Args:
        plan_id: UUID of the plan.
        current_user: Authenticated user.
        request: Apply request, optionally specifying budget_units.
        repository: Injected PlanRepository instance.
        db: Database session, passed through to the executor.

    Returns:
        The plan's current persisted state after this apply invocation.

    Raises:
        HTTPException: 404 if the plan does not exist or is not owned by
            the current user.
    """
    plan = repository.get_by_id(plan_id, user_id=current_user.id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Plan not found: {plan_id}")

    budget_units = request.budget_units if request.budget_units is not None else settings.youtube_default_apply_budget

    logger.info(
        "Applying plan %s for user=%s with budget_units=%d",
        plan_id, current_user.id, budget_units,
    )
    apply_plan(plan_id=plan_id, user_id=current_user.id, budget_units=budget_units, db=db)

    updated_plan = repository.get_by_id(plan_id, user_id=current_user.id)
    if updated_plan is None:
        logger.error("Plan %s disappeared during apply for user=%s", plan_id, current_user.id)
        raise HTTPException(status_code=404, detail=f"Plan not found: {plan_id}")

    ops = repository.get_ops_for_plan(plan_id)
    return _to_plan_response(updated_plan, ops)
