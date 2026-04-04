from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class Message(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    source: str
    target: str
    payload: dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    msg_type: str = "data"  # "data", "review_request", "risk_assessment", "revision_request", "control"
