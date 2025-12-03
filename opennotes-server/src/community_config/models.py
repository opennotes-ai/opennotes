from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.llm_config.models import CommunityServer
    from src.users.models import User


class CommunityConfig(Base):
    """Store per-community-server bot configuration settings.

    This table stores configuration values for each community server (Discord server/guild,
    Reddit subreddit, Slack workspace, etc.), allowing community administrators
    to customize bot behavior.

    Foreign key constraint ensures that configuration records cannot exist
    for non-existent community servers. CASCADE delete ensures configuration
    is automatically cleaned up when a community server is deleted.
    """

    __tablename__ = "community_config"

    community_server_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("community_servers.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
        index=True,
    )
    config_key: Mapped[str] = mapped_column(String(128), primary_key=True, nullable=False)
    config_value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False, index=True
    )
    updated_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    community_server: Mapped["CommunityServer"] = relationship(
        back_populates="configs", lazy="selectin"
    )
    updated_by_user: Mapped["User"] = relationship("User", lazy="selectin")

    __table_args__ = (
        Index(
            "ix_community_config_community_server_id_key",
            "community_server_id",
            "config_key",
            unique=True,
        ),
    )


from src.llm_config.models import CommunityServer  # noqa: E402
from src.users.models import User  # noqa: E402
