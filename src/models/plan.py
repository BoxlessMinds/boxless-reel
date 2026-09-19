"""SQLAlchemy models for the generic plan/apply execution engine.

`Plan` and `PlanOp` are the journaled, resumable unit of work every
playlist-mutation strategy (create, dedupe, purge, copy, add, move, reorder)
plugs into. This module defines the generic executor
schema only — no concrete `Plan.kind` / `PlanOp.op_type` values are defined
here; those are introduced by the strategies that generate real plans.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Plan(Base):
    """A journaled batch of operations awaiting or undergoing apply.

    Creating a `Plan` never touches the YouTube API or the quota ledger —
    only `apply_plan` does. `status` tracks the plan as a whole through
    ``pending`` -> ``applying`` -> ``done``/``failed``; a killed process can
    re-invoke apply on a plan still in ``applying`` and resume safely,
    since individual op status (see `PlanOp`) is what actually drives
    resumption.

    `kind` is deliberately an unconstrained string: this story ships no
    concrete plan-generation strategy, so no closed set of kinds exists yet.
    Future stories (dedupe, purge, copy, ...) each introduce their own
    `kind` value.
    """

    __tablename__ = "plans"

    STATUSES = ("pending", "applying", "done", "failed")

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # "pending" | "applying" | "done" | "failed"
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    budget_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    ops: Mapped[list["PlanOp"]] = relationship(
        "PlanOp",
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="PlanOp.sequence",
    )

    def __repr__(self) -> str:
        """Return string representation of the plan."""
        return f"<Plan(id={self.id}, kind={self.kind!r}, status={self.status!r})>"


class PlanOp(Base):
    """A single step within a `Plan`, executed in `sequence` order.

    `status` is the resumption mechanism: `apply_plan` filters for ops that
    are not yet ``"done"`` and resumes from there, so no op executes twice.
    ``"pending"`` is the resumable start state; ``"done"`` means the op's
    `result` was persisted and its `actual_units` counted against the
    quota ledger; ``"skipped"`` means a non-retryable 4xx was tolerated
    without halting the plan; ``"failed"`` means retries were exhausted and
    the apply loop halted.

    `payload` carries the op's input and may reference a prior op's output
    via a placeholder shaped ``{"kind": "ref", "ref_sequence": N}`` in place
    of a literal value anywhere in the payload dict. Such a placeholder is
    resolved only from the referenced op's `result`, and only once that
    op's `status` is ``"done"`` — never from a `pending`, `skipped`, or
    `failed` op, and never from an in-memory value that was not actually
    persisted.

    `op_type` is deliberately an unconstrained string, mirroring `Plan.kind`:
    this story defines no concrete op types.
    """

    __tablename__ = "plan_ops"
    __table_args__ = (
        UniqueConstraint("plan_id", "sequence", name="uq_plan_op_sequence"),
    )

    STATUSES = ("pending", "done", "skipped", "failed")

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("plans.id"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    op_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # "pending" | "done" | "skipped" | "failed"
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    depends_on_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actual_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    plan: Mapped["Plan"] = relationship("Plan", back_populates="ops")

    def __repr__(self) -> str:
        """Return string representation of the plan op."""
        return (
            f"<PlanOp(id={self.id}, plan_id={self.plan_id}, "
            f"sequence={self.sequence}, status={self.status!r})>"
        )
