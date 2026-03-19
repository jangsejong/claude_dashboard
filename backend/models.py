from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UsageRecord(BaseModel):
    user_name: str
    machine: str
    project: Optional[str] = None
    model: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    session_id: Optional[str] = None
    message_uuid: Optional[str] = None
    created_at: Optional[datetime] = None


class UsageRecordWithTotal(UsageRecord):
    total_tokens: int = Field(description="input_tokens + output_tokens")


class UsagePostResponse(BaseModel):
    ok: bool = True
    saved_count: int = 0
    saved_ids: list[int] = Field(default_factory=list)
