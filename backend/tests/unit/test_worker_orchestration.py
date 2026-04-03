"""Unit tests for worker orchestration seams."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.core.automation.platforms.base import JobListing
from app.workers.orchestration.artifacts import ArtifactOrchestrator
from app.workers.orchestration.state_transition import StateTransitionOrchestrator
from app.workers.orchestration.submission import SubmissionOrchestrator
from app.workers.orchestration.verification import VerificationOrchestrator


class TestVerificationOrchestrator:
    def test_verify_platform_unknown(self) -> None:
        registry = MagicMock()
        registry.has.return_value = False
        verifier = VerificationOrchestrator(session_factory=MagicMock(), platform_registry=registry)

        result = verifier.verify_platform("unknown")

        assert result.ok is False
        assert "Unknown platform" in result.error

    def test_verify_ats_threshold_failure(self) -> None:
        result = VerificationOrchestrator.verify_ats_threshold(0.5, 0.75)

        assert result.ok is False
        assert "below minimum threshold" in result.error


class TestStateTransitionOrchestrator:
    async def test_fail_updates_and_broadcasts(self) -> None:
        update = AsyncMock()
        broadcast = AsyncMock()
        transitions = StateTransitionOrchestrator(
            update_status=update,
            broadcast_progress=broadcast,
        )

        await transitions.fail(
            "app-1",
            detail="boom",
            notes="boom",
            ats_score=0.4,
        )

        update.assert_awaited_once()
        broadcast.assert_awaited_once()


class TestSubmissionOrchestrator:
    async def test_submit_handles_platform_false(self) -> None:
        platform = AsyncMock()
        platform.apply = AsyncMock(return_value=False)

        registry = MagicMock()
        registry.create.return_value = platform

        orchestrator = SubmissionOrchestrator(platform_registry=registry)
        result = await orchestrator.submit(
            platform_name="linkedin",
            job=JobListing(
                platform="linkedin",
                platform_job_id="ext-1",
                title="Role",
                company="Co",
            ),
            resume_path="/tmp/resume.pdf",
            cover_letter_path=None,
        )

        assert result.success is False
        assert "unsuccessful" in result.error


class TestArtifactOrchestrator:
    async def test_generate_for_application_without_resume(self) -> None:
        orchestrator = ArtifactOrchestrator(
            session_factory=MagicMock(),
            resume_service=MagicMock(),
        )

        result = await orchestrator.generate_for_application(
            job_id="job-1",
            resume_id="",
        )

        assert result.resume_path is None


    async def test_generate_for_application_uses_selected_resume_without_tailoring(self) -> None:
        orchestrator = ArtifactOrchestrator(
            session_factory=MagicMock(),
            resume_service=MagicMock(),
        )

        mock_db = AsyncMock()
        orchestrator.session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        orchestrator.session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        selected_resume = MagicMock(id="r1", file_path_pdf="/tmp/r1.pdf", file_path_docx=None)

        from unittest.mock import patch

        with patch("app.workers.orchestration.artifacts.select_best_resume_for_job", new_callable=AsyncMock) as mock_select:
            mock_select.return_value = MagicMock(
                selected_resume=selected_resume,
                should_tailor=False,
                reason="best_existing_tailored_selected",
            )

            result = await orchestrator.generate_for_application(job_id="job-1", resume_id="base-1")

        assert result.resume_path == "/tmp/r1.pdf"
        assert result.resume_id == "r1"
        assert result.decision_reason == "best_existing_tailored_selected"
