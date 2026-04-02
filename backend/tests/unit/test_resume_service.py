"""Unit tests for resume service helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from sqlalchemy.exc import IntegrityError

from app.services.resume import _create_resume_version


class TestCreateResumeVersion:
    async def test_retries_on_unique_conflict_and_succeeds(self) -> None:
        db = Mock()
        db.execute = AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(version=1)),
                SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(version=2)),
            ]
        )
        db.add = Mock()
        db.commit = AsyncMock(side_effect=[IntegrityError("stmt", {}, Exception("dup")), None])
        db.rollback = AsyncMock()

        resume = SimpleNamespace(
            id="resume-1",
            job_id="job-1",
            template_id="modern",
            file_path_pdf="/tmp/out.pdf",
            file_path_docx="/tmp/out.docx",
            content_text="content",
            ats_score=0.91,
        )

        await _create_resume_version(
            db=db,
            resume=resume,
            candidate_id="candidate-1",
            variant_type="tailored",
            label="Tailored Resume",
        )

        assert db.commit.await_count == 2
        db.rollback.assert_awaited_once()
        assert db.add.call_count == 2

    async def test_skips_when_candidate_id_missing(self) -> None:
        db = Mock()
        db.execute = AsyncMock()
        db.add = Mock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        resume = SimpleNamespace()

        await _create_resume_version(
            db=db,
            resume=resume,
            candidate_id=None,
            variant_type="base",
            label="Base Resume",
        )

        db.execute.assert_not_called()
        db.add.assert_not_called()
        db.commit.assert_not_called()
