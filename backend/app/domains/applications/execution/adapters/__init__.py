"""Execution adapters for application attempts."""

from .base import (
    AdapterCapability,
    AdapterFailureClass,
    AdapterRisk,
    FailureCategory,
    ArtifactRecord,
    ExecutionAdapter,
    ExecutionContext,
    ExecutionResult,
    VerificationResult,
)
from .platform_apply import PlatformApplyAdapter

__all__ = [
    "AdapterCapability",
    "AdapterFailureClass",
    "AdapterRisk",
    "FailureCategory",
    "ArtifactRecord",
    "ExecutionAdapter",
    "ExecutionContext",
    "ExecutionResult",
    "VerificationResult",
    "PlatformApplyAdapter",
]
