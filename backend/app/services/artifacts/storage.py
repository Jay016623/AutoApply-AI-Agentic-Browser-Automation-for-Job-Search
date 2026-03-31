"""Artifact storage abstraction with local backend and cloud-ready interface."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config.settings import get_settings


@dataclass(slots=True, frozen=True)
class StoredArtifact:
    """Persisted artifact metadata returned by storage backends."""

    storage_path: str
    checksum: str
    size_bytes: int
    backend: str


class ArtifactStorage:
    """Storage backend contract for proof artifacts."""

    backend_name = "base"

    async def store_bytes(
        self,
        *,
        tenant_id: str | None,
        attempt_id: str | None,
        attempt_step_id: str | None,
        artifact_type: str,
        payload: bytes,
        extension: str,
    ) -> StoredArtifact:
        raise NotImplementedError

    async def store_json(
        self,
        *,
        tenant_id: str | None,
        attempt_id: str | None,
        attempt_step_id: str | None,
        artifact_type: str,
        payload: dict[str, Any],
    ) -> StoredArtifact:
        data = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        return await self.store_bytes(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            attempt_step_id=attempt_step_id,
            artifact_type=artifact_type,
            payload=data,
            extension="json",
        )


class LocalArtifactStorage(ArtifactStorage):
    """Filesystem-backed storage for local development and test environments."""

    backend_name = "local"

    def __init__(self, root_dir: str) -> None:
        self._root = Path(root_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    async def store_bytes(
        self,
        *,
        tenant_id: str | None,
        attempt_id: str | None,
        attempt_step_id: str | None,
        artifact_type: str,
        payload: bytes,
        extension: str,
    ) -> StoredArtifact:
        now = datetime.now(UTC)
        tenant_segment = tenant_id or "tenant-unknown"
        attempt_segment = attempt_id or "attempt-unknown"
        step_segment = attempt_step_id or "step-global"
        safe_type = artifact_type.replace("/", "-").replace(" ", "_")
        directory = self._root / tenant_segment / attempt_segment / step_segment
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{now.strftime('%Y%m%dT%H%M%S%fZ')}_{safe_type}.{extension}"
        file_path = directory / filename
        file_path.write_bytes(payload)

        checksum = hashlib.sha256(payload).hexdigest()
        size_bytes = len(payload)
        return StoredArtifact(
            storage_path=file_path.as_posix(),
            checksum=checksum,
            size_bytes=size_bytes,
            backend=self.backend_name,
        )


def get_artifact_storage() -> ArtifactStorage:
    """Return configured storage backend.

    Today this supports local filesystem storage. Provider wiring is additive so
    S3/GCS backends can be introduced without changing worker orchestration.
    """

    settings = get_settings()
    provider = settings.artifact_storage_provider
    if provider == "local":
        return LocalArtifactStorage(settings.artifact_storage_local_root)
    raise ValueError(f"Unsupported artifact storage provider: {provider}")
