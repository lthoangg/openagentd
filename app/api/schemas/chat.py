"""Form bodies for POST /api/chat and POST /api/team/chat."""

from __future__ import annotations

from fastapi import Form, HTTPException
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.api.schemas.base import _validation_detail

# ── Form models (multipart/form-data) ────────────────────────────────────────
#
# FastAPI < 1.0 cannot combine ``Annotated[Model, Form()]`` with ``File()``
# in the same endpoint.  The ``as_form`` classmethod works around this by
# reading individual Form() fields and constructing the validated model
# via ``Depends(Model.as_form)``.


class ChatForm(BaseModel):
    """Validated form body for POST /api/chat and POST /api/team/chat.

    Modes (mutually exclusive):
    - **Normal send** (interrupt=false, message required)
    - **Interrupt** (interrupt=true, session_id required, no message)
    """

    message: str | None = Field(None, description="The user's message.")
    session_id: str | None = Field(
        None, description="Resume an existing session by UUID."
    )
    interrupt: bool = Field(
        False,
        description="Interrupt the running agent. Mutually exclusive with message.",
    )

    @classmethod
    def as_form(
        cls,
        message: str | None = Form(None),
        session_id: str | None = Form(None),
        interrupt: bool = Form(False),
    ) -> "ChatForm":
        try:
            return cls(message=message, session_id=session_id, interrupt=interrupt)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422, detail=_validation_detail(exc)
            ) from exc

    @model_validator(mode="after")
    def _validate_message_or_interrupt(self) -> "ChatForm":
        if self.interrupt and self.message:
            raise ValueError("interrupt and message are mutually exclusive.")
        if self.interrupt and not self.session_id:
            raise ValueError("session_id is required when interrupt=true.")
        if not self.interrupt and not self.message:
            raise ValueError("message is required when interrupt=false.")
        if self.message is not None and len(self.message.strip()) == 0:
            raise ValueError("message must not be blank.")
        return self
