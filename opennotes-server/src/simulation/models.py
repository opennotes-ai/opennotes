from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pendulum
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base
from src.notes.models import TimestampMixin

if TYPE_CHECKING:
    from src.users.profile_models import UserProfile


class SimAgent(Base, TimestampMixin):
    __tablename__ = "opennotes_sim_agents"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    personality: Mapped[str] = mapped_column(Text, nullable=False)
    short_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_params: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    tool_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    memory_compaction_strategy: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="sliding_window"
    )
    memory_compaction_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_sim_agents_deleted_at", "deleted_at"),
        CheckConstraint(
            "memory_compaction_strategy IN ('sliding_window', 'summarize_and_prune', 'semantic_dedup')",
            name="ck_sim_agents_memory_compaction_strategy",
        ),
    )

    @hybrid_property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        self.deleted_at = pendulum.now("UTC")


class SimAgentMemory(Base, TimestampMixin):
    __tablename__ = "sim_agent_memories"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    agent_instance_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sim_agent_instances.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_compacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    compaction_strategy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    recent_actions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    seen_request_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    agent_instance: Mapped[SimAgentInstance] = relationship(
        "SimAgentInstance", back_populates="memory", lazy="raise"
    )

    __table_args__ = (
        Index(
            "idx_sim_agent_memories_agent_instance_id",
            "agent_instance_id",
            unique=True,
        ),
    )


class SimChannelMessage(Base, TimestampMixin):
    __tablename__ = "sim_channel_messages"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    simulation_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_instance_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sim_agent_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_text: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("idx_sim_channel_messages_run_created", "simulation_run_id", "created_at"),
    )


class SimulationOrchestrator(Base, TimestampMixin):
    __tablename__ = "simulation_orchestrators"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    community_server_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("community_servers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    turn_cadence_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")
    max_agents: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")
    removal_rate: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="0.0",
    )
    max_turns_per_agent: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    agent_profile_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    scoring_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_simulation_orchestrators_deleted_at", "deleted_at"),
        Index("idx_simulation_orchestrators_is_active", "is_active"),
        CheckConstraint("turn_cadence_seconds > 0", name="ck_orchestrator_cadence_positive"),
        CheckConstraint("max_agents > 0", name="ck_orchestrator_max_agents_positive"),
        CheckConstraint(
            "removal_rate >= 0 AND removal_rate <= 1",
            name="ck_orchestrator_removal_rate_range",
        ),
        CheckConstraint("max_turns_per_agent > 0", name="ck_orchestrator_max_turns_positive"),
    )

    @hybrid_property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        self.deleted_at = pendulum.now("UTC")


class SimulationRunConfig(Base, TimestampMixin):
    __tablename__ = "simulation_run_configs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    simulation_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    restart_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_turns_per_agent: Mapped[int] = mapped_column(Integer, nullable=False)
    turn_cadence_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    max_agents: Mapped[int] = mapped_column(Integer, nullable=False)
    removal_rate: Mapped[float] = mapped_column(Float, nullable=False)
    scoring_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index(
            "idx_simulation_run_configs_run_restart",
            "simulation_run_id",
            "restart_number",
        ),
    )


class SimulationRun(Base, TimestampMixin):
    __tablename__ = "simulation_runs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    orchestrator_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("simulation_orchestrators.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    community_server_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("community_servers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, server_default=text("'{}'::jsonb")
    )
    config_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    cumulative_turns: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    restart_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    current_config_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("simulation_run_configs.id", ondelete="SET NULL"),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    orchestrator: Mapped[SimulationOrchestrator] = relationship(
        "SimulationOrchestrator", lazy="raise"
    )
    agent_instances: Mapped[list[SimAgentInstance]] = relationship(
        back_populates="simulation_run",
        lazy="raise",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_simulation_runs_deleted_at", "deleted_at"),
        Index("idx_simulation_runs_status", "status"),
        Index("idx_simulation_runs_orchestrator_status", "orchestrator_id", "status"),
        Index("idx_simulation_runs_is_public", "is_public"),
        CheckConstraint(
            "status IN ('pending', 'running', 'paused', 'completed', 'cancelled', 'failed')",
            name="ck_simulation_runs_status",
        ),
    )

    @hybrid_property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        self.deleted_at = pendulum.now("UTC")


class SimAgentRunLog(Base, TimestampMixin):
    __tablename__ = "sim_agent_run_logs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    agent_instance_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    simulation_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    restart_number: Mapped[int] = mapped_column(Integer, nullable=False)
    turns_in_segment: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    state_at_end: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "idx_sim_agent_run_logs_instance_restart",
            "agent_instance_id",
            "restart_number",
        ),
        Index(
            "idx_sim_agent_run_logs_run_id",
            "simulation_run_id",
        ),
    )


class SimAgentInstance(Base, TimestampMixin):
    __tablename__ = "sim_agent_instances"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    simulation_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("opennotes_sim_agents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    state: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_turn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    removal_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cumulative_turn_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    current_run_log_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sim_agent_run_logs.id", ondelete="SET NULL"),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    simulation_run: Mapped[SimulationRun] = relationship(
        "SimulationRun", back_populates="agent_instances", lazy="raise"
    )
    agent_profile: Mapped[SimAgent] = relationship("SimAgent", lazy="raise")
    user_profile: Mapped[UserProfile] = relationship("UserProfile", lazy="raise")
    memory: Mapped[SimAgentMemory | None] = relationship(
        "SimAgentMemory", back_populates="agent_instance", uselist=False, lazy="raise"
    )

    __table_args__ = (
        Index("idx_sim_agent_instances_deleted_at", "deleted_at"),
        Index("idx_sim_agent_instances_state", "state"),
        Index("idx_sim_agent_instances_run_state", "simulation_run_id", "state"),
        CheckConstraint(
            "state IN ('active', 'paused', 'completed', 'removed')",
            name="ck_sim_agent_instances_state",
        ),
        CheckConstraint(
            "turn_count >= 0",
            name="ck_sim_agent_instances_turn_count_nonneg",
        ),
    )

    @hybrid_property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        self.deleted_at = pendulum.now("UTC")
