"""Pydantic API schemas -- request/response models for all endpoints."""

from app.schemas.analytics import (
    ApplicationFunnelData,
    ATSScoreDistribution,
    DashboardStats,
    LLMUsageStats,
    TimelineEntry,
)
from app.schemas.application import (
    ApplicationBatchCreate,
    ApplicationCreate,
    ApplicationListResponse,
    ApplicationResponse,
    ApplicationStatusUpdate,
)
from app.schemas.job import (
    JobAnalysisResponse,
    JobListingResponse,
    JobListResponse,
    JobSearchRequest,
)
from app.schemas.candidate import (
    CandidateCreate,
    CandidateListResponse,
    CandidateProfileSnapshotCreate,
    CandidateProfileSnapshotResponse,
    CandidateResponse,
    CandidateSettingsSchema,
    CandidateUpdate,
    CoverLetterVersionResponse,
    ResumeVersionResponse,
)
from app.schemas.resume import (
    ResumeGenerateRequest,
    ResumeListResponse,
    ResumeResponse,
    ResumeScoreRequest,
    ResumeScoreResponse,
    ResumeUploadResponse,
)
from app.schemas.settings import LLMProviderStatus, SettingsResponse, SettingsUpdate
from app.schemas.review import ReviewActionRequest, ReviewTaskListResponse, ReviewTaskResponse
from app.schemas.execution import (
    ArtifactDownloadUrlResponse,
    ExecutionAttemptListResponse,
    ExecutionAttemptResponse,
    ExecutionStepResponse,
    ProofArtifactListResponse,
    ProofArtifactResponse,
    TimelineEventResponse,
    TimelineResponse,
)

__all__ = [
    "ATSScoreDistribution",
    # application
    "ApplicationBatchCreate",
    "ApplicationCreate",
    # analytics
    "ApplicationFunnelData",
    "ApplicationListResponse",
    "ApplicationResponse",
    "ApplicationStatusUpdate",
    "DashboardStats",
    "ProofArtifactResponse",
    "ProofArtifactListResponse",
    "ExecutionStepResponse",
    "ExecutionAttemptResponse",
    "ExecutionAttemptListResponse",
    "ArtifactDownloadUrlResponse",
    "TimelineResponse",
    "TimelineEventResponse",
    # candidate
    "CandidateCreate",
    "CandidateListResponse",
    "CandidateProfileSnapshotCreate",
    "CandidateProfileSnapshotResponse",
    "CandidateResponse",
    "CandidateSettingsSchema",
    "CandidateUpdate",
    "CoverLetterVersionResponse",
    # job
    "JobAnalysisResponse",
    "JobListResponse",
    "JobListingResponse",
    "JobSearchRequest",
    # settings
    "LLMProviderStatus",
    "LLMUsageStats",
    # resume
    "ResumeGenerateRequest",
    "ResumeListResponse",
    "ResumeResponse",
    "ResumeScoreRequest",
    "ResumeScoreResponse",
    "ResumeUploadResponse",
    "ResumeVersionResponse",
    "SettingsResponse",
    "SettingsUpdate",
    "TimelineEntry",
    "ReviewTaskResponse",
    "ReviewActionRequest",
    "ReviewTaskListResponse",
]
