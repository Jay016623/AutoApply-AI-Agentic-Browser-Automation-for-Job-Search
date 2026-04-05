"""User settings API routes with database persistence."""

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, get_db, get_tenant_context
from app.config.settings import get_settings as get_app_settings
from app.models.user_settings import UserSettings
from app.schemas.settings import LLMProviderStatus, SettingsResponse, SettingsUpdate

logger = structlog.get_logger(__name__)
router = APIRouter()


async def _get_or_create_settings(
    db: AsyncSession,
    tenant_id: str | None = None,
) -> UserSettings:
    """Get tenant-scoped settings, with read-only legacy fallback for null tenant."""
    if tenant_id:
        result = await db.execute(
            select(UserSettings).where(UserSettings.tenant_id == tenant_id),
        )
        settings = result.scalar_one_or_none()
        if settings is not None:
            return settings

        legacy_result = await db.execute(
            select(UserSettings)
            .where(UserSettings.tenant_id.is_(None))
            .order_by(UserSettings.created_at.asc())
            .limit(1),
        )
        legacy = legacy_result.scalar_one_or_none()

        if legacy is None:
            settings = UserSettings(tenant_id=tenant_id)
        else:
            # Legacy fallback is read-only template behavior.
            settings = UserSettings(
                tenant_id=tenant_id,
                apply_mode=legacy.apply_mode,
                max_parallel=legacy.max_parallel,
                min_ats_score=legacy.min_ats_score,
                preferred_provider=legacy.preferred_provider,
                platforms_enabled=legacy.platforms_enabled,
                candidate_profile=legacy.candidate_profile,
            )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
        logger.info("settings_created_for_tenant", tenant_id=tenant_id)
        return settings

    result = await db.execute(
        select(UserSettings)
        .where(UserSettings.tenant_id.is_(None))
        .order_by(UserSettings.created_at.asc())
        .limit(1),
    )
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = UserSettings(tenant_id=None)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
        logger.info("settings_created_legacy_defaults")
    return settings


@router.get(
    "/",
    response_model=SettingsResponse,
    summary="Get current settings",
)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> SettingsResponse:
    """Get the current user settings from the database."""
    settings = await _get_or_create_settings(db, tenant_id=tenant_ctx.tenant_id)
    return SettingsResponse.model_validate(settings)


@router.put(
    "/",
    response_model=SettingsResponse,
    summary="Update settings",
)
async def update_settings(
    update: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> SettingsResponse:
    """Update user settings. Only provided fields are changed."""
    settings = await _get_or_create_settings(db, tenant_id=tenant_ctx.tenant_id)

    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(settings, field, value)

    await db.commit()
    await db.refresh(settings)

    logger.info("settings_updated", changed_fields=list(update_data.keys()))
    return SettingsResponse.model_validate(settings)


@router.get(
    "/llm-providers",
    response_model=list[LLMProviderStatus],
    summary="List LLM provider statuses",
)
async def list_llm_providers() -> list[LLMProviderStatus]:
    """List configured LLM providers and their real configuration status."""
    settings = get_app_settings()
    llm = settings.llm

    providers_config = [
        ("openai", llm.openai_api_key, "gpt-4o"),
        ("groq", llm.groq_api_key, "llama-3.1-70b-versatile"),
        ("gemini", llm.gemini_api_key, "gemini-pro"),
        ("openrouter", llm.openrouter_api_key, llm.default_model),
        ("github", llm.github_token, "gpt-4o"),
    ]

    return [
        LLMProviderStatus(
            provider=name,
            configured=bool(key.get_secret_value()),
            model=model,
            is_primary=llm.preferred_provider == name,
        )
        for name, key, model in providers_config
    ]
