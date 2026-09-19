"""Repository for plan and plan-op database operations."""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.plan import Plan, PlanOp

logger = logging.getLogger(__name__)


class PlanRepository:
    """Data access layer for `Plan` / `PlanOp` records.

    Query-only: no budget arithmetic, no retry policy, no ref-placeholder
    resolution. Those decisions belong to `plan_apply_service` (the
    executor) and to whichever future story's plan-generation service
    creates the rows in the first place.
    """

    def __init__(self, db: Session) -> None:
        """
        Initialize repository with database session.

        Args:
            db: SQLAlchemy database session.
        """
        self.db = db

    # -- Plan -----------------------------------------------------------

    def create_plan(self, plan: Plan) -> Plan:
        """
        Persist a new plan.

        Args:
            plan: Plan model instance to persist.

        Returns:
            The persisted plan with generated ID.
        """
        logger.debug("Creating plan (user_id=%s, kind=%s)", plan.user_id, plan.kind)
        self.db.add(plan)
        self.db.commit()
        self.db.refresh(plan)
        logger.debug("Created plan with id: %s", plan.id)
        return plan

    def get_by_id(self, plan_id: str, user_id: str | None = None) -> Plan | None:
        """
        Get a plan by its ID.

        Args:
            plan_id: ID of the plan.
            user_id: Optional user ID to filter by ownership.

        Returns:
            Plan if found, None otherwise.
        """
        logger.debug("Fetching plan by id: %s (user_id=%s)", plan_id, user_id)
        stmt = select(Plan).where(Plan.id == plan_id)
        if user_id:
            stmt = stmt.where(Plan.user_id == user_id)
        result = self.db.execute(stmt).scalar_one_or_none()
        if result is None:
            logger.debug("Plan not found: %s", plan_id)
        return result

    def update_plan_status(self, plan_id: str, status: str) -> Plan | None:
        """
        Update a plan's status.

        Args:
            plan_id: ID of the plan.
            status: New status value — one of `Plan.STATUSES`
                ("pending", "applying", "done", "failed").

        Returns:
            The updated plan, or None if no plan matches `plan_id`.
        """
        logger.debug("Updating plan %s status -> %s", plan_id, status)
        plan = self.get_by_id(plan_id)
        if plan is None:
            logger.debug("Plan not found for status update: %s", plan_id)
            return None
        plan.status = status
        self.db.commit()
        self.db.refresh(plan)
        return plan

    # -- PlanOp -----------------------------------------------------------

    def create_ops(self, ops: list[PlanOp]) -> list[PlanOp]:
        """
        Persist a batch of plan ops in a single commit.

        Args:
            ops: PlanOp model instances to persist, typically all belonging
                to the same plan.

        Returns:
            The persisted ops with generated IDs, in the order given.
        """
        logger.debug("Creating %d plan ops", len(ops))
        self.db.add_all(ops)
        self.db.commit()
        for op in ops:
            self.db.refresh(op)
        logger.debug("Created %d plan ops", len(ops))
        return ops

    def get_op_by_id(self, op_id: str) -> PlanOp | None:
        """
        Get a plan op by its ID.

        Args:
            op_id: ID of the plan op.

        Returns:
            PlanOp if found, None otherwise.
        """
        logger.debug("Fetching plan op by id: %s", op_id)
        stmt = select(PlanOp).where(PlanOp.id == op_id)
        result = self.db.execute(stmt).scalar_one_or_none()
        if result is None:
            logger.debug("Plan op not found: %s", op_id)
        return result

    def get_ops_for_plan(self, plan_id: str) -> list[PlanOp]:
        """
        Get all ops belonging to a plan, ordered by sequence.

        Args:
            plan_id: ID of the owning plan.

        Returns:
            List of plan ops ordered by ascending sequence.
        """
        logger.debug("Fetching ops for plan: %s", plan_id)
        stmt = (
            select(PlanOp)
            .where(PlanOp.plan_id == plan_id)
            .order_by(PlanOp.sequence.asc())
        )
        results = list(self.db.execute(stmt).scalars().all())
        logger.debug("Found %d ops for plan %s", len(results), plan_id)
        return results

    def get_ops_by_status(self, plan_id: str, statuses: list[str]) -> list[PlanOp]:
        """
        Get a plan's ops whose status is in `statuses`, ordered by sequence.

        Used by the apply loop to resume: passing `["pending"]` (or
        `["pending", "failed"]`, depending on the executor's retry policy)
        yields exactly the ops still needing work, so an op already
        `"done"` is never re-executed.

        Args:
            plan_id: ID of the owning plan.
            statuses: Status values to include — members of `PlanOp.STATUSES`.

        Returns:
            List of matching plan ops ordered by ascending sequence.
        """
        logger.debug(
            "Fetching ops for plan %s with status in %s", plan_id, statuses
        )
        stmt = (
            select(PlanOp)
            .where(PlanOp.plan_id == plan_id, PlanOp.status.in_(statuses))
            .order_by(PlanOp.sequence.asc())
        )
        results = list(self.db.execute(stmt).scalars().all())
        logger.debug("Found %d matching ops for plan %s", len(results), plan_id)
        return results

    def get_op_by_sequence(self, plan_id: str, sequence: int) -> PlanOp | None:
        """
        Get a single op within a plan by its sequence number.

        Used to resolve a `{"kind": "ref", "ref_sequence": N}` payload
        placeholder — the caller must check the returned op's `status ==
        "done"` before trusting its `result`; this method does not filter
        by status.

        Args:
            plan_id: ID of the owning plan.
            sequence: The op's sequence number within the plan.

        Returns:
            PlanOp if found, None otherwise.
        """
        logger.debug(
            "Fetching op by sequence (plan_id=%s, sequence=%d)", plan_id, sequence
        )
        stmt = select(PlanOp).where(
            PlanOp.plan_id == plan_id, PlanOp.sequence == sequence
        )
        result = self.db.execute(stmt).scalar_one_or_none()
        if result is None:
            logger.debug(
                "Op not found (plan_id=%s, sequence=%d)", plan_id, sequence
            )
        return result

    def update_op_status(
        self,
        op_id: str,
        status: str,
        **fields: Any,
    ) -> PlanOp | None:
        """
        Update a plan op's status and any accompanying result fields.

        Args:
            op_id: ID of the plan op.
            status: New status value — one of `PlanOp.STATUSES`
                ("pending", "done", "skipped", "failed").
            **fields: Additional column values to set (e.g. `result`,
                `actual_units`, `error_message`, `executed_at`).

        Returns:
            The updated plan op, or None if no op matches `op_id`.
        """
        logger.debug("Updating plan op %s status -> %s", op_id, status)
        op = self.get_op_by_id(op_id)
        if op is None:
            logger.debug("Plan op not found for status update: %s", op_id)
            return None
        op.status = status
        for key, value in fields.items():
            setattr(op, key, value)
        self.db.commit()
        self.db.refresh(op)
        return op
