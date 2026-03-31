"""Tests for artifact storage abstraction."""

from pathlib import Path

from app.services.artifacts.storage import LocalArtifactStorage


class TestLocalArtifactStorage:
    async def test_store_json_writes_file_and_checksum(self, tmp_path: Path):
        storage = LocalArtifactStorage(str(tmp_path / "artifacts"))

        stored = await storage.store_json(
            tenant_id="tenant-1",
            attempt_id="attempt-1",
            attempt_step_id="step-1",
            artifact_type="verification_evidence",
            payload={"current_url": "https://example.com/confirmation", "submitted": True},
        )

        file_path = Path(stored.storage_path)
        assert stored.backend == "local"
        assert stored.size_bytes > 0
        assert file_path.exists()
        assert "tenant-1" in stored.storage_path
        assert "attempt-1" in stored.storage_path
