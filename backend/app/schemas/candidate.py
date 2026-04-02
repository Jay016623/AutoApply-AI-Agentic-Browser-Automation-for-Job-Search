"""Pydantic schemas for candidate domain APIs."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CandidateSettingsSchema(BaseModel):
    """Candidate-specific preferences and defaults."""

    default_resume_template: str = "modern"
    default_cover_letter_template: str = "standard"
    target_roles: list[str] = Field(default_factory=list)
    target_locations: list[str] = Field(default_factory=list)
    remote_only: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidateCreate(BaseModel):
    """Request body for creating a candidate."""

    tenant_id: str | None = None
    full_name: str = Field(..., min_length=1, max_length=200)
    email: str
    phone: str | None = None
    location: str | None = None
    headline: str | None = None
    is_default: bool = False
    settings: CandidateSettingsSchema = Field(default_factory=CandidateSettingsSchema)


class CandidateUpdate(BaseModel):
    """Partial candidate update request."""

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    headline: str | None = None
    is_active: bool | None = None
    is_default: bool | None = None


class CandidateResponse(BaseModel):
    """Candidate response DTO."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str | None = None
    full_name: str
    email: str
    phone: str | None = None
    location: str | None = None
    headline: str | None = None
    is_active: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime


class CandidateListResponse(BaseModel):
    """Candidate list response."""

    items: list[CandidateResponse]
    total: int


class CandidateProfileSnapshotCreate(BaseModel):
    """Create candidate profile snapshot request."""

    source: str = "manual"
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[dict[str, Any]] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    snapshot_metadata: dict[str, Any] = Field(default_factory=dict)


class CandidateProfileSnapshotResponse(BaseModel):
    """Candidate profile snapshot response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str | None = None
    candidate_id: str
    version: int
    source: str
    summary: str
    skills: list[Any]
    experience: list[Any]
    education: list[Any]
    certifications: list[Any]
    snapshot_metadata: dict[str, Any] | None = None
    created_at: datetime


class ResumeVersionResponse(BaseModel):
    """Resume version response DTO."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    candidate_id: str
    version: int
    label: str
    template_id: str
    variant_type: str
    job_id: str | None = None
    ats_score: float | None = None
    has_pdf: bool = False
    has_docx: bool = False
    created_at: datetime


class CoverLetterVersionResponse(BaseModel):
    """Cover letter version response DTO."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    candidate_id: str
    version: int
    label: str
    template_id: str
    job_id: str | None = None
    has_pdf: bool = False
    has_docx: bool = False
    created_at: datetime
