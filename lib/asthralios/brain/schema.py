from pydantic import BaseModel, Field
from typing import Literal, Optional, Any
from datetime import datetime

# ── Top-level classification result ──────────────────────────────────────────

BrainCategory = Literal["people", "projects", "ideas", "admin", "musings"]

class ClassificationResult(BaseModel):
    category: BrainCategory
    confidence: float = Field(..., ge=0.0, le=1.0)
    name: str
    next_action: Optional[str] = None
    payload: dict  # category-specific fields, validated downstream
    raw_message: str
    classified_at: datetime = Field(default_factory=datetime.utcnow)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None

# ── Per-category schemas ──────────────────────────────────────────────────────

class PersonEntry(BaseModel):
    name: str
    next_action: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    labels: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)  # **kwargs equivalent

class ProjectEntry(BaseModel):
    name: str
    next_action: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[Literal["low", "medium", "high", "critical"]] = None
    timeline: Optional[str] = None

class IdeaEntry(BaseModel):
    name: str
    next_action: Optional[str] = None
    premise: Optional[str] = None
    source: Optional[str] = None
    direction: Optional[str] = None

class AdminEntry(BaseModel):
    name: str
    next_action: Optional[str] = None
    due: Optional[str] = None  # free-form date/time string

class MusingEntry(BaseModel):
    name: str
    next_action: Optional[str] = None
    blob: str  # full freeform text dump

class EventEntry(BaseModel):
    title: str
    name: str  # alias for title, required for uniformity
    next_action: Optional[str] = None
    description: Optional[str] = None
    when: Optional[str] = None  # ISO 8601 or natural language

# ── Inbox log record ──────────────────────────────────────────────────────────

class InboxLogRecord(BaseModel):
    id: Optional[int] = None
    received_at: datetime
    source_platform: str           # "slack" | "discord"
    source_user: str
    source_channel: str
    raw_message: str
    category: Optional[str] = None
    name: Optional[str] = None
    confidence: Optional[float] = None
    filed_path: Optional[str] = None
    status: Literal["filed", "needs_review", "fix_applied"] = "filed"
    clarification_question: Optional[str] = None
    fix_original_category: Optional[str] = None
