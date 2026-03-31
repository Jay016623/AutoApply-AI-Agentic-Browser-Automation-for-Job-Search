"""Deterministic execution adapter primitives for application submission.

This layer contains unstable browser automation behind a structured interface so
worker orchestration can reason over capabilities, risks, and failures.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.automation.platforms.base import JobListing


class AdapterRisk(str, Enum):
    """Qualitative risk level for adapter execution path."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AdapterFailureClass(str, Enum):
    """Normalized failure categories returned by execution adapters."""

    NONE = "none"
    RETRYABLE = "retryable"
    MANUAL_CHECKPOINT = "manual_checkpoint"
    UNSUPPORTED = "unsupported"


@dataclass(slots=True, frozen=True)
class AdapterCapability:
    """Capability metadata for orchestration and observability."""

    adapter_name: str
    platforms: tuple[str, ...]
    supports_cover_letter: bool = False
    supports_multi_step_flows: bool = True
    risk: AdapterRisk = AdapterRisk.HIGH
    deterministic_guarantees: tuple[str, ...] = (
        "bounded-step-contract",
        "structured-failure-classification",
    )


@dataclass(slots=True, frozen=True)
class ExecutionContext:
    """Input contract passed from orchestration into adapter."""

    tenant_id: str | None
    application_id: str
    workflow_run_id: str | None
    attempt_id: str
    platform_name: str
    job_listing: JobListing
    resume_path: str
    cover_letter_path: str | None = None
    manual_checkpoint_mode: bool = False
    manual_checkpoint_reason: str | None = None


@dataclass(slots=True)
class ExecutionResult:
    """Structured adapter execution output."""

    success: bool
    submitted: bool
    needs_manual_checkpoint: bool = False
    unsupported: bool = False
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class VerificationResult:
    """Result of deterministic verification step."""

    verified: bool
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class ArtifactRecord:
    """Proof artifact descriptor emitted by adapter."""

    artifact_type: str
    storage_path: str
    metadata: dict[str, Any] = field(default_factory=dict)


class ExecutionAdapter(ABC):
    """Deterministic wrapper for fragile platform automation."""

    @property
    @abstractmethod
    def capability(self) -> AdapterCapability:
        ...

    @abstractmethod
    def supports(self, context: ExecutionContext) -> bool:
        ...

    @abstractmethod
    async def prepare(self, context: ExecutionContext) -> ExecutionContext:
        ...

    @abstractmethod
    async def execute(self, context: ExecutionContext) -> ExecutionResult:
        ...

    @abstractmethod
    def verify(self, result: ExecutionResult) -> VerificationResult:
        ...

    @abstractmethod
    def collect_artifacts(self, result: ExecutionResult) -> list[ArtifactRecord]:
        ...

    @abstractmethod
    def classify_failure(self, result: ExecutionResult) -> AdapterFailureClass:
        ...
