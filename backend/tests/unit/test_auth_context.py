"""Tests for auth context and hard tenant enforcement."""

import pytest
from fastapi import HTTPException

from app.api.deps import get_auth_context
from app.config.settings import get_settings


class DummySession:
    async def execute(self, *_args, **_kwargs):
        class R:
            def scalar_one_or_none(self):
                return None
        return R()


@pytest.mark.asyncio
async def test_auth_context_allows_missing_headers_when_enforcement_off(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings.feature_flags, "tenant_enforcement", False)

    ctx = await get_auth_context(
        db=DummySession(),
        x_user_id=None,
        x_tenant_id=None,
        x_role=None,
    )
    assert ctx.enforced is False
    assert ctx.tenant_id is None


@pytest.mark.asyncio
async def test_auth_context_requires_headers_when_enforcement_on(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings.feature_flags, "tenant_enforcement", True)

    with pytest.raises(HTTPException):
        await get_auth_context(
            db=DummySession(),
            x_user_id=None,
            x_tenant_id=None,
            x_role=None,
        )
