"""Integration tests for candidate API endpoints."""

import pytest


@pytest.mark.asyncio
async def test_candidate_crud_and_settings(client) -> None:
    create_resp = await client.post(
        "/api/v1/candidates/",
        json={
            "tenant_id": "tenant-1",
            "full_name": "Alice Smith",
            "email": "alice@example.com",
        },
    )
    assert create_resp.status_code == 201
    candidate = create_resp.json()

    list_resp = await client.get("/api/v1/candidates/")
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] >= 1

    settings_resp = await client.put(
        f"/api/v1/candidates/{candidate['id']}/settings",
        json={
            "default_resume_template": "executive",
            "default_cover_letter_template": "technical",
            "target_roles": ["Principal Engineer"],
            "target_locations": ["Remote"],
            "remote_only": True,
            "metadata": {"source": "test"},
        },
    )
    assert settings_resp.status_code == 200
    assert settings_resp.json()["default_resume_template"] == "executive"
