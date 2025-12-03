from enum import IntEnum
from typing import Any, TypedDict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.common.base_schemas import StrictEventSchema, StrictInputSchema


class InteractionType(IntEnum):
    PING = 1
    APPLICATION_COMMAND = 2
    MESSAGE_COMPONENT = 3
    APPLICATION_COMMAND_AUTOCOMPLETE = 4
    MODAL_SUBMIT = 5


class InteractionResponseType(IntEnum):
    PONG = 1
    CHANNEL_MESSAGE_WITH_SOURCE = 4
    DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE = 5
    DEFERRED_UPDATE_MESSAGE = 6
    UPDATE_MESSAGE = 7
    APPLICATION_COMMAND_AUTOCOMPLETE_RESULT = 8
    MODAL = 9


class EmbedFooter(BaseModel):
    text: str = Field(..., max_length=2048, description="Footer text")
    icon_url: str | None = Field(None, description="Footer icon URL")


class EmbedImage(BaseModel):
    url: str = Field(..., description="Image URL")


class EmbedThumbnail(BaseModel):
    url: str = Field(..., description="Thumbnail URL")


class EmbedAuthor(BaseModel):
    name: str = Field(..., max_length=256, description="Author name")
    url: str | None = Field(None, description="Author URL")
    icon_url: str | None = Field(None, description="Author icon URL")


class EmbedField(BaseModel):
    name: str = Field(..., max_length=256, description="Field name")
    value: str = Field(..., max_length=1024, description="Field value")
    inline: bool = Field(False, description="Whether field should be inline")


class Embed(BaseModel):
    title: str | None = Field(None, max_length=256, description="Embed title")
    description: str | None = Field(None, max_length=4096, description="Embed description")
    url: str | None = Field(None, description="Embed URL")
    color: int | None = Field(None, description="Color code")
    footer: EmbedFooter | None = None
    image: EmbedImage | None = None
    thumbnail: EmbedThumbnail | None = None
    author: EmbedAuthor | None = None
    fields: list[EmbedField] | None = Field(None, max_length=25)


class AllowedMentions(BaseModel):
    parse: list[str] = Field(
        default_factory=list,
        description="Parse types: 'roles', 'users', 'everyone'",
    )
    roles: list[str] = Field(default_factory=list, description="Role IDs to mention")
    users: list[str] = Field(default_factory=list, description="User IDs to mention")
    replied_user: bool = Field(False, description="Whether to mention replied user")


class Attachment(BaseModel):
    id: str | None = Field(None, description="Attachment ID")
    filename: str = Field(..., description="File name")
    description: str | None = Field(None, description="Description")
    content_type: str | None = Field(None, description="MIME type")
    size: int | None = Field(None, description="Size in bytes")
    url: str | None = Field(None, description="URL of attachment")


class InteractionCallbackData(BaseModel):
    content: str | None = None
    embeds: list[Embed] | None = None
    allowed_mentions: AllowedMentions | None = None
    flags: int | None = None
    components: list[dict[str, Any]] | None = Field(
        None,
        description="Message components. Keep as dict - Discord API structures vary by component type",
    )
    attachments: list[Attachment] | None = None


class InteractionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    type: int = Field(..., description="Interaction response type")
    data: InteractionCallbackData | None = None


class DiscordUser(BaseModel):
    id: str
    username: str
    discriminator: str
    avatar: str | None = None


class DiscordMember(BaseModel):
    user: DiscordUser | None = None
    nick: str | None = None
    roles: list[str] = Field(default_factory=list)


class InteractionData(BaseModel):
    id: str | None = None
    name: str | None = None
    type: int | None = None
    options: list[dict[str, Any]] | None = None
    custom_id: str | None = None
    components: list[dict[str, Any]] | None = None
    values: list[str] | None = None


class DiscordInteraction(StrictEventSchema):
    id: str
    application_id: str
    type: int
    data: InteractionData | None = None
    community_server_id: str | None = None
    channel_id: str | None = None
    member: DiscordMember | None = None
    user: DiscordUser | None = None
    token: str
    version: int = 1
    message: dict[str, Any] | None = None

    @property
    def user_id(self) -> str:
        if self.member and self.member.user:
            return self.member.user.id
        if self.user:
            return self.user.id
        return "unknown"

    @property
    def command_name(self) -> str | None:
        if self.data:
            return self.data.name
        return None


class WebhookConfig(BaseModel):
    id: UUID | None = None
    url: str
    secret: str
    community_server_id: str
    channel_id: str | None = None
    active: bool = True

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        use_enum_values=True,
        extra="forbid",
    )


class WebhookConfigResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        use_enum_values=True,
    )

    id: UUID
    url: str
    community_server_id: str
    channel_id: str | None = None
    active: bool


class WebhookConfigSecure(WebhookConfigResponse):
    secret: str


class WebhookCreateRequest(StrictInputSchema):
    url: str = Field(..., description="Webhook URL")
    secret: str = Field(..., description="Webhook secret")
    community_server_id: str = Field(
        ..., description="Community server ID (Discord guild ID, subreddit name, etc.)"
    )
    channel_id: str | None = Field(None, description="Channel ID (Discord channel ID, etc.)")


class WebhookUpdateRequest(StrictInputSchema):
    url: str | None = None
    secret: str | None = None
    channel_id: str | None = None
    active: bool | None = None


class TaskStatus(BaseModel):
    task_id: str
    interaction_id: str
    task_type: str
    status: str
    result: dict[str, Any] | None = Field(
        None,
        description="Task result data. Kept as dict - structure varies by task type",
    )
    error: str | None = None
    retry_count: int
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


class BaseTaskData(TypedDict):
    interaction_id: str
    interaction_token: str
    application_id: str
    community_server_id: str | None
    channel_id: str | None
    user_id: str
    data: dict[str, Any] | None


class CommandTaskData(BaseTaskData):
    command_name: str | None


class ComponentTaskData(BaseTaskData):
    custom_id: str


class ModalTaskData(BaseTaskData):
    custom_id: str


class QueueTaskData(TypedDict):
    id: str
    type: str
    data: dict[str, Any]


class CommandResultData(TypedDict, total=False):
    command: str
    processed_at: str


class ComponentResultData(TypedDict, total=False):
    custom_id: str
    processed_at: str


class ModalResultData(TypedDict, total=False):
    custom_id: str
    processed_at: str
