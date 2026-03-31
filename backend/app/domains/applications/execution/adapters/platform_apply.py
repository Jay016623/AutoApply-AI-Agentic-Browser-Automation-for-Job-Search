"""Execution adapter for current platform.apply flow.

This is intentionally conservative: it wraps existing browser automation without
claiming deterministic browser outcomes. Determinism is limited to control-flow,
result shape, and failure classification.
"""

from __future__ import annotations

from app.core.automation.platforms import platform_registry
from app.domains.applications.execution.adapters.base import (
    AdapterCapability,
    AdapterFailureClass,
    AdapterRisk,
    ArtifactRecord,
    ExecutionAdapter,
    ExecutionContext,
    ExecutionResult,
    VerificationResult,
)


class PlatformApplyAdapter(ExecutionAdapter):
    """Adapter for single-step submit via existing platform plugin apply()."""

    @property
    def capability(self) -> AdapterCapability:
        return AdapterCapability(
            adapter_name="platform_apply_v1",
            platforms=("linkedin", "indeed", "glassdoor"),
            supports_cover_letter=False,
            supports_multi_step_flows=False,
            risk=AdapterRisk.HIGH,
            deterministic_guarantees=(
                "bounded-execute-contract",
                "explicit-unsupported-manual-checkpoint",
                "failure-classification-no-silent-failure",
            ),
        )

    def supports(self, context: ExecutionContext) -> bool:
        return platform_registry.has(context.platform_name)

    async def prepare(self, context: ExecutionContext) -> ExecutionContext:
        # Keep prepare deterministic and side-effect-free for now.
        return context

    async def execute(self, context: ExecutionContext) -> ExecutionResult:
        if context.manual_checkpoint_mode:
            return ExecutionResult(
                success=False,
                submitted=False,
                needs_manual_checkpoint=True,
                error_code="MANUAL_CHECKPOINT",
                error_message=context.manual_checkpoint_reason
                or "manual checkpoint mode enabled",
                metadata={"mode": "manual_checkpoint"},
            )

        if not self.supports(context):
            return ExecutionResult(
                success=False,
                submitted=False,
                needs_manual_checkpoint=True,
                unsupported=True,
                error_code="UNSUPPORTED_PLATFORM",
                error_message=f"Unsupported execution adapter platform: {context.platform_name}",
                metadata={"platform": context.platform_name},
            )

        platform = platform_registry.create(context.platform_name)
        applied = await platform.apply(
            job=context.job_listing,
            resume_path=context.resume_path,
            cover_letter_path=context.cover_letter_path,
        )
        if not applied:
            return ExecutionResult(
                success=False,
                submitted=False,
                error_code="PLATFORM_APPLY_FAILED",
                error_message="Platform returned unsuccessful apply result",
                metadata={"platform": context.platform_name},
            )

        return ExecutionResult(
            success=True,
            submitted=True,
            metadata={"platform": context.platform_name},
        )

    def verify(self, result: ExecutionResult) -> VerificationResult:
        # Deterministic in contract only; verification remains weak because
        # plugin apply() lacks durable platform-side receipt validation.
        if result.submitted and result.success:
            return VerificationResult(verified=True)
        return VerificationResult(verified=False, reason=result.error_message)

    def collect_artifacts(self, result: ExecutionResult) -> list[ArtifactRecord]:
        artifacts = [
            ArtifactRecord(
                artifact_type="trace",
                storage_path=f"attempt://adapter/{self.capability.adapter_name}/trace",
                metadata={
                    "platform": result.metadata.get("platform", "unknown"),
                    "success": result.success,
                },
            ),
        ]
        if result.error_code:
            artifacts.append(
                ArtifactRecord(
                    artifact_type="log",
                    storage_path=f"attempt://adapter/{self.capability.adapter_name}/failure",
                    metadata={"error_code": result.error_code, "error_message": result.error_message or ""},
                ),
            )
        return artifacts

    def classify_failure(self, result: ExecutionResult) -> AdapterFailureClass:
        if result.success:
            return AdapterFailureClass.NONE
        if result.unsupported:
            return AdapterFailureClass.UNSUPPORTED
        if result.needs_manual_checkpoint or result.error_code == "MANUAL_CHECKPOINT":
            return AdapterFailureClass.MANUAL_CHECKPOINT
        return AdapterFailureClass.RETRYABLE
