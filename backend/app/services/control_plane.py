"""Tenant plan, quota, and feature control-plane helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Float, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, Role, ensure_role, require_tenant
from app.models.application import Application
from app.models.application_attempt import ApplicationAttempt
from app.models.candidate import Candidate
from app.models.llm_usage import LLMUsage
from app.models.proof_artifact import ProofArtifact
from app.models.tenant import Tenant
from app.services.audit import AuditLogCreate, record_audit_log


PLAN_CATALOG: dict[str, dict] = {
    "free": {
        "quotas": {
            "candidate_count": 5,
            "daily_applications": 25,
            "artifact_storage_bytes": 500_000_000,
            "automation_concurrency": 1,
            "llm_daily_tokens": 80_000,
            "llm_daily_cost_usd": 2.0,
        },
        "features": {
            "advanced_execution_diagnostics": False,
            "priority_automation": False,
            "custom_llm_models": False,
            "bulk_operations": False,
        },
    },
    "pro": {
        "quotas": {
            "candidate_count": 100,
            "daily_applications": 500,
            "artifact_storage_bytes": 20_000_000_000,
            "automation_concurrency": 5,
            "llm_daily_tokens": 1_000_000,
            "llm_daily_cost_usd": 50.0,
        },
        "features": {
            "advanced_execution_diagnostics": True,
            "priority_automation": True,
            "custom_llm_models": True,
            "bulk_operations": True,
        },
    },
    "enterprise": {
        "quotas": {
            "candidate_count": 10_000,
            "daily_applications": 20_000,
            "artifact_storage_bytes": 500_000_000_000,
            "automation_concurrency": 50,
            "llm_daily_tokens": 25_000_000,
            "llm_daily_cost_usd": 2_000.0,
        },
        "features": {
            "advanced_execution_diagnostics": True,
            "priority_automation": True,
            "custom_llm_models": True,
            "bulk_operations": True,
        },
    },
}


class QuotaExceededError(ValueError):
    """Raised when a tenant exceeds a plan quota."""


@dataclass(frozen=True)
class TenantPlanSnapshot:
    tenant_id: str
    plan_key: str
    quotas: dict[str, float]
    features: dict[str, bool]


async def _get_tenant(db: AsyncSession, tenant_id: str) -> Tenant:
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    if tenant is None:
        raise ValueError("tenant_not_found")
    return tenant


async def get_tenant_plan_snapshot(db: AsyncSession, tenant_id: str) -> TenantPlanSnapshot:
    tenant = await _get_tenant(db, tenant_id)
    plan_key = tenant.plan_key if tenant.plan_key in PLAN_CATALOG else "free"
    base = PLAN_CATALOG[plan_key]
    quotas = dict(base["quotas"])
    features = dict(base["features"])

    if isinstance(tenant.plan_overrides, dict):
        for key, value in tenant.plan_overrides.items():
            if key in quotas:
                quotas[key] = float(value)
    if isinstance(tenant.feature_overrides, dict):
        for key, value in tenant.feature_overrides.items():
            if key in features:
                features[key] = bool(value)

    return TenantPlanSnapshot(
        tenant_id=tenant_id,
        plan_key=plan_key,
        quotas=quotas,
        features=features,
    )


def _day_bounds() -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start, end


async def _usage_snapshot(db: AsyncSession, tenant_id: str) -> dict[str, float]:
    start, end = _day_bounds()
    candidate_count = int((await db.execute(select(func.count(Candidate.id)).where(Candidate.tenant_id == tenant_id))).scalar() or 0)
    daily_applications = int(
        (
            await db.execute(
                select(func.count(Application.id)).where(
                    Application.tenant_id == tenant_id,
                    Application.created_at >= start,
                    Application.created_at <= end,
                ),
            )
        ).scalar()
        or 0
    )
    storage_bytes = int(
        (await db.execute(select(func.coalesce(func.sum(ProofArtifact.size_bytes), 0)).where(ProofArtifact.tenant_id == tenant_id))).scalar()
        or 0
    )
    running_automation = int(
        (
            await db.execute(
                select(func.count(ApplicationAttempt.id)).where(
                    ApplicationAttempt.tenant_id == tenant_id,
                    ApplicationAttempt.status == "running",
                ),
            )
        ).scalar()
        or 0
    )
    llm_daily_tokens = int(
        (
            await db.execute(
                select(func.coalesce(func.sum(LLMUsage.total_tokens), 0)).where(
                    LLMUsage.tenant_id == tenant_id,
                    LLMUsage.created_at >= start,
                    LLMUsage.created_at <= end,
                ),
            )
        ).scalar()
        or 0
    )
    llm_daily_cost = float(
        (
            await db.execute(
                select(func.coalesce(func.sum(cast(LLMUsage.cost_usd, Float)), 0.0)).where(
                    LLMUsage.tenant_id == tenant_id,
                    LLMUsage.created_at >= start,
                    LLMUsage.created_at <= end,
                ),
            )
        ).scalar()
        or 0.0
    )
    return {
        "candidate_count": float(candidate_count),
        "daily_applications": float(daily_applications),
        "artifact_storage_bytes": float(storage_bytes),
        "automation_concurrency": float(running_automation),
        "llm_daily_tokens": float(llm_daily_tokens),
        "llm_daily_cost_usd": llm_daily_cost,
    }


async def get_tenant_quota_status(db: AsyncSession, tenant_id: str) -> dict:
    plan = await get_tenant_plan_snapshot(db, tenant_id)
    usage = await _usage_snapshot(db, tenant_id)
    quotas = {
        key: {
            "limit": plan.quotas[key],
            "used": usage.get(key, 0.0),
            "remaining": max(plan.quotas[key] - usage.get(key, 0.0), 0.0),
            "exceeded": usage.get(key, 0.0) > plan.quotas[key],
        }
        for key in plan.quotas
    }
    return {
        "tenant_id": tenant_id,
        "plan_key": plan.plan_key,
        "features": plan.features,
        "quotas": quotas,
    }


async def enforce_quota(
    db: AsyncSession,
    *,
    tenant_id: str,
    quota_key: str,
    increment: float = 1.0,
    actor_id: str | None = None,
    actor_type: str = "system",
    context: dict | None = None,
) -> None:
    plan = await get_tenant_plan_snapshot(db, tenant_id)
    if quota_key not in plan.quotas:
        raise ValueError(f"unknown_quota:{quota_key}")

    usage = await _usage_snapshot(db, tenant_id)
    current = usage.get(quota_key, 0.0)
    projected = current + increment
    limit = float(plan.quotas[quota_key])

    if projected <= limit:
        return

    await record_audit_log(
        db,
        AuditLogCreate(
            tenant_id=tenant_id,
            actor_id=actor_id,
            actor_type=actor_type,
            entity_type="tenant",
            entity_id=tenant_id,
            event_type="quota.exceeded",
            status="blocked",
            message=f"quota_key={quota_key} projected={projected} limit={limit}",
            event_metadata={
                "quota_key": quota_key,
                "current": current,
                "projected": projected,
                "limit": limit,
                "context": context or {},
            },
        ),
    )
    raise QuotaExceededError(f"quota_exceeded:{quota_key}")


async def require_feature(
    db: AsyncSession,
    *,
    tenant_id: str,
    feature_key: str,
    actor_id: str | None = None,
) -> None:
    plan = await get_tenant_plan_snapshot(db, tenant_id)
    if plan.features.get(feature_key, False):
        return

    await record_audit_log(
        db,
        AuditLogCreate(
            tenant_id=tenant_id,
            actor_id=actor_id,
            entity_type="tenant",
            entity_id=tenant_id,
            event_type="feature.denied",
            status="blocked",
            message=f"feature={feature_key}",
            event_metadata={"feature_key": feature_key, "plan_key": plan.plan_key},
        ),
    )
    raise QuotaExceededError(f"feature_not_enabled:{feature_key}")


async def update_tenant_plan(
    db: AsyncSession,
    *,
    tenant_id: str,
    plan_key: str,
    plan_overrides: dict | None,
    feature_overrides: dict | None,
    auth: AuthContext,
) -> Tenant:
    ensure_role(auth, {Role.OWNER, Role.ADMIN})
    if plan_key not in PLAN_CATALOG:
        raise ValueError("unsupported_plan")
    tenant = await _get_tenant(db, tenant_id)
    tenant.plan_key = plan_key
    tenant.plan_overrides = plan_overrides
    tenant.feature_overrides = feature_overrides
    await db.commit()
    await db.refresh(tenant)

    await record_audit_log(
        db,
        AuditLogCreate(
            tenant_id=tenant.id,
            actor_id=auth.user_id,
            actor_type="user",
            entity_type="tenant",
            entity_id=tenant.id,
            event_type="plan.updated",
            message=f"plan={plan_key}",
            event_metadata={
                "plan_key": plan_key,
                "plan_overrides": plan_overrides,
                "feature_overrides": feature_overrides,
                "request_id": uuid4().hex,
            },
        ),
    )
    return tenant


async def get_current_tenant_quota_status(db: AsyncSession, auth: AuthContext) -> dict:
    tenant_id = require_tenant(auth)
    return await get_tenant_quota_status(db, tenant_id)
