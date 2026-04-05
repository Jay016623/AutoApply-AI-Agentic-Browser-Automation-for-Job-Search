"""Integration tests for the Settings API routes."""



API_PREFIX = "/api/v1/settings"


class TestGetSettings:
    """Tests for GET /api/v1/settings/."""

    async def test_get_default_settings(self, client):
        response = await client.get(f"{API_PREFIX}/")

        assert response.status_code == 200
        body = response.json()
        assert body["apply_mode"] == "review"
        assert body["min_ats_score"] == 0.75
        assert body["max_parallel"] == 3
        assert isinstance(body["platforms_enabled"], list)
        assert "linkedin" in body["platforms_enabled"]

    async def test_get_settings_is_tenant_keyed(self, client):
        legacy_before = await client.get(f"{API_PREFIX}/")
        assert legacy_before.status_code == 200

        resp_a = await client.put(
            f"{API_PREFIX}/",
            headers={"X-Tenant-Id": "tenant-a"},
            json={"apply_mode": "autonomous"},
        )
        assert resp_a.status_code == 200

        resp_b = await client.get(
            f"{API_PREFIX}/",
            headers={"X-Tenant-Id": "tenant-b"},
        )
        assert resp_b.status_code == 200
        assert resp_b.json()["apply_mode"] == "review"

        legacy_after = await client.get(f"{API_PREFIX}/")
        assert legacy_after.status_code == 200
        assert legacy_after.json()["apply_mode"] == legacy_before.json()["apply_mode"]


class TestUpdateSettings:
    """Tests for PUT /api/v1/settings/."""

    async def test_update_partial_settings(self, client):
        response = await client.put(
            f"{API_PREFIX}/",
            headers={"X-Tenant-Id": "tenant-a"},
            json={"apply_mode": "autonomous", "max_parallel": 5},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["apply_mode"] == "autonomous"
        assert body["max_parallel"] == 5
        # Unchanged fields should remain at defaults
        assert body["min_ats_score"] == 0.75

    async def test_update_min_ats_score(self, client):
        response = await client.put(
            f"{API_PREFIX}/",
            headers={"X-Tenant-Id": "tenant-a"},
            json={"min_ats_score": 0.9},
        )

        assert response.status_code == 200
        assert response.json()["min_ats_score"] == 0.9

    async def test_update_platforms_enabled(self, client):
        response = await client.put(
            f"{API_PREFIX}/",
            headers={"X-Tenant-Id": "tenant-a"},
            json={"platforms_enabled": ["linkedin"]},
        )

        assert response.status_code == 200
        assert response.json()["platforms_enabled"] == ["linkedin"]


class TestListLLMProviders:
    """Tests for GET /api/v1/settings/llm-providers."""

    async def test_list_providers_returns_defaults(self, client):
        response = await client.get(f"{API_PREFIX}/llm-providers")

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 5

        providers = {item["provider"] for item in body}
        assert "openai" in providers
        assert "groq" in providers
        assert "gemini" in providers

        for item in body:
            assert item["configured"] is False
            assert "model" in item
