"""Unit tests for API dependency helpers."""

import pytest
from fastapi import HTTPException

from app.api.deps import get_tenant_context


class _Flags:
    def __init__(self, tenant_enforcement: bool) -> None:
        self.tenant_enforcement = tenant_enforcement


class _Settings:
    def __init__(self, tenant_enforcement: bool) -> None:
        self.feature_flags = _Flags(tenant_enforcement=tenant_enforcement)


class TestTenantContextDependency:
    async def test_allows_missing_tenant_header_when_enforcement_disabled(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "app.api.deps.get_settings",
            lambda: _Settings(tenant_enforcement=False),
        )

        ctx = await get_tenant_context(x_tenant_id=None, x_actor_id="actor-1")
        assert ctx.tenant_id is None
        assert ctx.actor_id == "actor-1"
        assert ctx.enforced is False

    async def test_rejects_missing_tenant_header_when_enforcement_enabled(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "app.api.deps.get_settings",
            lambda: _Settings(tenant_enforcement=True),
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_tenant_context(x_tenant_id=None, x_actor_id="actor-1")

        assert exc_info.value.status_code == 400
        assert "X-Tenant-Id" in exc_info.value.detail
