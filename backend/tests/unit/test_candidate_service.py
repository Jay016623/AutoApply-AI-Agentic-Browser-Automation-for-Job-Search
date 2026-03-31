"""Unit tests for candidate service behavior."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.candidate.service import CandidateService
from app.models.cover_letter_version import CoverLetterVersion
from app.models.resume_version import ResumeVersion
from app.schemas.candidate import CandidateCreate, CandidateProfileSnapshotCreate, CandidateSettingsSchema


class TestCandidateService:
    """Validate candidate service CRUD and version queries."""

    async def test_create_and_get_candidate(self, db_session: AsyncSession) -> None:
        service = CandidateService(db_session)
        created = await service.create_candidate(
            CandidateCreate(
                tenant_id="tenant-1",
                full_name="Jane Doe",
                email="jane@example.com",
            )
        )

        fetched = await service.get_candidate(created.id)
        assert fetched.email == "jane@example.com"
        assert fetched.tenant_id == "tenant-1"

    async def test_create_profile_snapshot_increments_versions(
        self,
        db_session: AsyncSession,
    ) -> None:
        service = CandidateService(db_session)
        created = await service.create_candidate(
            CandidateCreate(
                tenant_id="tenant-1",
                full_name="Jane Doe",
                email="jane2@example.com",
            )
        )

        first = await service.create_profile_snapshot(
            created.id,
            CandidateProfileSnapshotCreate(summary="first"),
        )
        second = await service.create_profile_snapshot(
            created.id,
            CandidateProfileSnapshotCreate(summary="second"),
        )

        assert first.version == 1
        assert second.version == 2

    async def test_update_candidate_settings(self, db_session: AsyncSession) -> None:
        service = CandidateService(db_session)
        created = await service.create_candidate(
            CandidateCreate(
                tenant_id="tenant-1",
                full_name="Jane Doe",
                email="jane3@example.com",
            )
        )

        updated = await service.update_candidate_settings(
            created.id,
            CandidateSettingsSchema(
                default_resume_template="executive",
                target_roles=["Staff Engineer"],
                remote_only=True,
            ),
        )

        assert updated.default_resume_template == "executive"
        assert updated.target_roles == ["Staff Engineer"]
        assert updated.remote_only is True

    async def test_list_document_versions(self, db_session: AsyncSession) -> None:
        service = CandidateService(db_session)
        created = await service.create_candidate(
            CandidateCreate(
                tenant_id="tenant-1",
                full_name="Jane Doe",
                email="jane4@example.com",
            )
        )

        db_session.add(
            ResumeVersion(
                tenant_id="tenant-1",
                candidate_id=created.id,
                version=1,
                label="Base Resume",
                template_id="modern",
                variant_type="base",
            )
        )
        db_session.add(
            CoverLetterVersion(
                tenant_id="tenant-1",
                candidate_id=created.id,
                version=1,
                label="Cover v1",
                template_id="standard",
            )
        )
        await db_session.commit()

        resumes = await service.list_resume_versions(created.id)
        cover_letters = await service.list_cover_letter_versions(created.id)

        assert len(resumes) == 1
        assert resumes[0].label == "Base Resume"
        assert len(cover_letters) == 1
        assert cover_letters[0].label == "Cover v1"
