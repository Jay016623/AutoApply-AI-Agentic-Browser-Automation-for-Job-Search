"""Resume management API routes."""

from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    TenantContext,
    get_db,
    get_tenant_context,
    require_execution_write_tenant,
)
from app.core.exceptions import RecordNotFoundError
from app.schemas.resume import (
    ResumeGenerateRequest,
    ResumeListResponse,
    ResumeOptimizeRequest,
    ResumeResponse,
    ResumeScoreRequest,
    ResumeScoreResponse,
    ResumeUploadResponse,
)
from app.schemas.settings import CandidateProfileSchema
from app.services import resume as resume_service

logger = structlog.get_logger(__name__)
router = APIRouter()

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".pdf", ".docx"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.post(
    "/upload",
    response_model=ResumeUploadResponse,
    status_code=201,
    summary="Upload a resume file",
)
async def upload_resume(
    file: UploadFile,
    candidate_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> ResumeUploadResponse:
    """Upload a PDF or DOCX resume for parsing and storage."""
    # Validate file extension
    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Only PDF and DOCX files accepted, got '{file_ext}'",
        )

    # Validate MIME type
    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid file type: {file.content_type}",
        )

    # Validate file size by reading in chunks to avoid loading huge files into memory
    size = 0
    chunk_size = 64 * 1024  # 64KB
    while chunk := await file.read(chunk_size):
        size += len(chunk)
        if size > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="File too large. Max 10MB.")
    await file.seek(0)

    tenant_id = require_execution_write_tenant(tenant_ctx, tenant_ctx.tenant_id)
    return await resume_service.upload_resume(
        db,
        file,
        candidate_id=candidate_id,
        tenant_id=tenant_id,
    )


@router.get(
    "/",
    response_model=ResumeListResponse,
    summary="List all resumes",
)
async def list_resumes(
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> ResumeListResponse:
    """List all uploaded and generated resumes."""
    return await resume_service.list_resumes(db, tenant_id=tenant_ctx.tenant_id)


@router.post(
    "/generate",
    response_model=ResumeResponse,
    status_code=201,
    summary="Generate a tailored resume",
)
async def generate_resume(
    request: ResumeGenerateRequest,
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> ResumeResponse:
    """Generate a job-tailored resume from a base resume.

    Uses LLM to rewrite content. Placeholder until Phase 5.
    """
    tenant_id = require_execution_write_tenant(tenant_ctx, tenant_ctx.tenant_id)
    return await resume_service.generate_tailored_resume(db, request, tenant_id=tenant_id)


@router.post(
    "/{resume_id}/score",
    response_model=ResumeScoreResponse,
    summary="Score resume against a job",
)
async def score_resume(
    resume_id: str,
    request: ResumeScoreRequest,
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> ResumeScoreResponse:
    """Score a resume's ATS compatibility against a specific job."""
    return await resume_service.score_resume(
        db,
        resume_id,
        request,
        tenant_id=tenant_ctx.tenant_id,
    )


@router.post(
    "/{resume_id}/optimize",
    response_model=ResumeResponse,
    summary="Optimize resume for ATS",
)
async def optimize_resume(
    resume_id: str,
    request: ResumeOptimizeRequest = ResumeOptimizeRequest(),
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> ResumeResponse:
    """Optimize a resume for ATS keyword matching using LLM rewriting.

    Creates a new optimized resume linked to the original with improved
    ATS compatibility scores.
    """
    tenant_id = require_execution_write_tenant(tenant_ctx, tenant_ctx.tenant_id)
    return await resume_service.optimize_resume(
        db,
        resume_id,
        request.job_id,
        tenant_id=tenant_id,
    )


@router.get(
    "/{resume_id}/download",
    summary="Download resume file",
)
async def download_resume(
    resume_id: str,
    format: str = Query(default="pdf", pattern="^(pdf|docx)$"),
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> FileResponse:
    """Download a resume in PDF or DOCX format."""
    resume = await resume_service.get_resume(
        db, resume_id, tenant_id=tenant_ctx.tenant_id,
    )

    file_path = resume.file_path_pdf if format == "pdf" else resume.file_path_docx
    if not file_path or not Path(file_path).exists():
        raise RecordNotFoundError("Resume file", resume_id)

    media_type = (
        "application/pdf" if format == "pdf" else
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=f"{resume.name}.{format}",
    )


@router.get(
    "/{resume_id}/profile-data",
    response_model=CandidateProfileSchema,
    summary="Extract profile data from a resume",
)
async def extract_profile_from_resume(
    resume_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> CandidateProfileSchema:
    """Extract structured candidate profile data from a resume.

    Parses the resume's stored text content using DocumentParser's
    section extraction and contact info regex to build a structured
    CandidateProfile that can pre-fill the profile editor.
    """
    resume = await resume_service.get_resume(
        db, resume_id, tenant_id=tenant_ctx.tenant_id,
    )
    content = resume.content_text or ""

    if not content.strip():
        logger.warning("profile_extract_empty_resume", resume_id=resume_id)
        return CandidateProfileSchema()

    from app.core.documents.parser import DocumentParser

    parser = DocumentParser()
    contact = parser._extract_contact_info(content)
    sections = parser._extract_sections(content)
    skills = parser._extract_skills_from_text(content, sections)

    # Derive the full name from the first non-empty line before any section
    full_name = ""
    for line in content.split("\n"):
        stripped = line.strip()
        if (
            stripped
            and stripped.lower().rstrip(":") not in sections
            and "@" not in stripped
            and "http" not in stripped.lower()
        ):
            full_name = stripped
            break

    summary = ""
    for key in ("summary", "objective", "professional summary", "profile"):
        if key in sections:
            summary = sections[key]
            break

    certifications: list[str] = []
    for key in ("certifications", "certificates", "licenses"):
        if key in sections:
            cert_text = sections[key]
            certifications = [
                line.lstrip("-*\u2022\u2023 ").strip()
                for line in cert_text.split("\n")
                if line.strip()
            ]
            break

    logger.info(
        "profile_data_extracted",
        resume_id=resume_id,
        skills_count=len(skills),
        has_contact=bool(contact),
    )

    return CandidateProfileSchema(
        full_name=full_name,
        email=contact.get("email", ""),
        phone=contact.get("phone", ""),
        linkedin_url=contact.get("linkedin", ""),
        github_url=contact.get("github", ""),
        summary=summary,
        skills=skills,
        certifications=certifications,
    )
