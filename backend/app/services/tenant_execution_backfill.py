"""Planning helpers for tenant-ownership backfill of execution records."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.audit_log import AuditLog
from app.models.resume_version import ResumeVersion


@dataclass(frozen=True)
class ExecutionTenantBackfillPlan:
    """Counts of execution records lacking tenant ownership."""

    applications_missing_tenant: int
    resume_versions_missing_tenant: int
    audit_logs_missing_tenant: int


async def build_execution_tenant_backfill_plan(
    db: AsyncSession,
) -> ExecutionTenantBackfillPlan:
    """Compute null-tenant counts used to stage stricter ownership rollout."""
    app_missing = (
        await db.execute(
            select(func.count(Application.id)).where(Application.tenant_id.is_(None)),
        )
    ).scalar() or 0

    resume_versions_missing = (
        await db.execute(
            select(func.count(ResumeVersion.id)).where(ResumeVersion.tenant_id.is_(None)),
        )
    ).scalar() or 0

    audit_missing = (
        await db.execute(
            select(func.count(AuditLog.id)).where(AuditLog.tenant_id.is_(None)),
        )
    ).scalar() or 0

    return ExecutionTenantBackfillPlan(
        applications_missing_tenant=int(app_missing),
        resume_versions_missing_tenant=int(resume_versions_missing),
        audit_logs_missing_tenant=int(audit_missing),
    )
