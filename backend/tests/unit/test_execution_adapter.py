"""Unit tests for deterministic execution adapter wrapper."""

from unittest.mock import AsyncMock, patch

from app.core.automation.platforms.base import JobListing
from app.domains.applications.execution.adapters import (
    AdapterFailureClass,
    ExecutionContext,
    PlatformApplyAdapter,
)


def _context(platform: str = "linkedin", manual_mode: bool = False) -> ExecutionContext:
    return ExecutionContext(
        tenant_id="tenant-1",
        application_id="app-1",
        workflow_run_id="wf-1",
        attempt_id="attempt-1",
        platform_name=platform,
        job_listing=JobListing(
            platform=platform,
            platform_job_id="ext-1",
            title="Engineer",
            company="TestCo",
            location="Remote",
            url="https://example.com/job",
            description="desc",
            job_type="full-time",
            remote=True,
        ),
        resume_path="/tmp/resume.pdf",
        manual_checkpoint_mode=manual_mode,
        manual_checkpoint_reason="operator requested" if manual_mode else None,
    )


class TestPlatformApplyAdapter:
    async def test_manual_checkpoint_mode_returns_manual_classification(self):
        adapter = PlatformApplyAdapter()

        result = await adapter.execute(_context(manual_mode=True))

        assert result.success is False
        assert adapter.classify_failure(result) == AdapterFailureClass.MANUAL_CHECKPOINT

    async def test_unsupported_platform_returns_manual_checkpoint(self):
        adapter = PlatformApplyAdapter()
        with patch("app.domains.applications.execution.adapters.platform_apply.platform_registry") as mock_registry:
            mock_registry.has.return_value = False
            result = await adapter.execute(_context(platform="monster"))

        assert result.unsupported is True
        assert result.needs_manual_checkpoint is True
        assert adapter.classify_failure(result) == AdapterFailureClass.UNSUPPORTED

    async def test_platform_apply_false_is_retryable(self):
        adapter = PlatformApplyAdapter()
        mock_platform = AsyncMock()
        mock_platform.apply = AsyncMock(return_value=False)

        with patch("app.domains.applications.execution.adapters.platform_apply.platform_registry") as mock_registry:
            mock_registry.has.return_value = True
            mock_registry.create.return_value = mock_platform
            result = await adapter.execute(_context())

        assert result.success is False
        assert result.error_code == "PLATFORM_APPLY_FAILED"
        assert adapter.classify_failure(result) == AdapterFailureClass.RETRYABLE

    async def test_success_has_verification_and_artifacts(self):
        adapter = PlatformApplyAdapter()
        mock_platform = AsyncMock()
        mock_platform.apply = AsyncMock(return_value=True)

        with patch("app.domains.applications.execution.adapters.platform_apply.platform_registry") as mock_registry:
            mock_registry.has.return_value = True
            mock_registry.create.return_value = mock_platform
            result = await adapter.execute(_context())

        verification = adapter.verify(result)
        artifacts = adapter.collect_artifacts(result)

        assert result.success is True
        assert verification.verified is True
        assert len(artifacts) >= 1
        assert adapter.classify_failure(result) == AdapterFailureClass.NONE
