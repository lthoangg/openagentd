from datetime import datetime, timezone
from uuid import UUID, uuid7

from pydantic import BaseModel, Field, model_validator


class SummarizationConfig(BaseModel):
    """Per-agent summarization overrides.

    Any field left as ``None`` falls back to the global file config
    (``.openagentd/config/summarization.md``) and then to the module-level
    ``DEFAULT_*`` constants in ``app.agent.hooks.summarization``.
    Set ``enabled: false`` to disable summarization for this agent entirely.
    """

    enabled: bool = True
    # Overrides file config / DEFAULT_PROMPT_TOKEN_THRESHOLD.
    token_threshold: int | None = None
    # Overrides file config / DEFAULT_KEEP_LAST_ASSISTANTS.
    keep_last_assistants: int | None = None
    # Overrides file config / DEFAULT_MAX_TOKEN_LENGTH.
    max_token_length: int | None = None
    model: str | None = None  # optional separate summarizer model (provider:model)


class SummarizationFileConfig(BaseModel):
    """Global summarization defaults loaded from ``.openagentd/config/summarization.md``.

    All fields are optional; missing fields fall back to the module-level
    ``DEFAULT_*`` constants in ``app.agent.hooks.summarization``.  The file
    uses YAML frontmatter; the Markdown body (after the closing ``---``)
    becomes the summariser system prompt when non-empty.
    """

    model: str | None = None  # global default summarizer model (provider:model)
    token_threshold: int | None = None
    keep_last_assistants: int | None = None
    max_token_length: int | None = None
    # Populated from the file body by the loader — not a YAML frontmatter field.
    # ``None`` means "body was empty, use the bundled default prompt".
    prompt: str | None = None


class TitleGenerationFileConfig(BaseModel):
    """Global title-generation defaults loaded from ``.openagentd/config/title_generation.md``.

    The file uses YAML frontmatter; the Markdown body (after the closing
    ``---``) is the title-generator system prompt. Title generation only
    runs when the file exists, ``enabled`` is ``true``, and the body is
    non-empty — otherwise a warning is logged and the feature is skipped
    (sessions keep their raw-truncation fallback title).

    Fields
    ------
    enabled:
        Feature switch. ``false`` disables title generation entirely (with
        a warning at startup). Default ``true``.
    model:
        Provider:model string for the dedicated title LLM. Defaults to the
        lead agent's own provider when omitted.
    wait_timeout_seconds:
        Best-effort cap (seconds) on how long ``after_agent`` will await the
        background title task before the agent loop completes. Set to ``0``
        to skip the wait entirely (fully non-blocking — the title still lands
        via SSE whenever it is ready). Default ``3.0``.
    prompt:
        Populated from the file body by the loader — not a YAML frontmatter
        field. ``None`` means the body was empty.
    """

    enabled: bool = True
    model: str | None = None
    wait_timeout_seconds: float | None = None
    prompt: str | None = None


class AgentStats(BaseModel):
    """Cumulative per-agent statistics, updated after each :meth:`~app.core.agent.Agent.run` call.

    Accessible as ``agent.state``.  This is distinct from
    :class:`~app.core.state.AgentState` which is the *per-run* mutable state
    passed to hooks.
    """

    agent_id: UUID
    status: str = "idle"  # idle, running, completed
    messages_count: int = 0
    total_tokens: int = 0


class RunConfig(BaseModel):
    """Per-run configuration passed to Agent.run().

    This is the *input* configuration for a single run.  Runtime mutable
    state is held in :class:`~app.core.state.AgentState` which is created
    automatically at the start of each ``Agent.run()`` call.

    Example::

        config = RunConfig(session_id="conv_abc123", metadata={"user_id": 42})
        messages = await agent.run(messages, config=config)
    """

    session_id: str | None = None
    run_id: str = Field(default_factory=lambda: str(uuid7()))
    parent_run_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    # Decoded from session_id automatically by the model validator below.
    # Frozen at session creation — used by dynamic_prompt to inject a stable
    # "current date" that does not drift across messages in the same session.
    session_created_at: datetime | None = None

    @model_validator(mode="after")
    def _decode_session_created_at(self) -> "RunConfig":
        """Decode session_created_at from the UUIDv7 session_id if not already set.

        UUIDv7 embeds a millisecond-precision Unix timestamp in the top 48 bits.
        Silently skips non-UUID session_id values (e.g. synthetic test ids).
        """
        if self.session_created_at is None and self.session_id is not None:
            try:
                ts_ms = UUID(self.session_id).int >> 80
                self.session_created_at = datetime.fromtimestamp(
                    ts_ms / 1000, tz=timezone.utc
                )
            except ValueError:
                pass
        return self


class AgentContext(BaseModel):
    """Base class for agent runtime context.

    Subclass this to add typed, validated fields that hooks and tools can
    read to shape agent behaviour (e.g. user role, locale, feature flags).
    An instance is passed via ``Agent(context=...)`` and is accessible
    through ``state.context`` inside hooks and injected tool parameters.

    Example::

        class UserContext(AgentContext):
            user_id: int
            user_group: str = "default"
            locale: str = "en"

        agent = Agent(
            llm_provider=provider,
            context=UserContext(user_id=42, user_group="premium"),
            hooks=[inject_current_date],
        )
    """
