"""Artifact storage abstraction with local and S3-compatible backends."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config.settings import get_settings
from app.db.session import async_session_factory
from app.observability.metrics import artifact_storage_bytes_total
from app.services import control_plane

_SAFE_SEGMENT_PATTERN = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe_segment(value: str | None, *, default: str) -> str:
    normalized = _SAFE_SEGMENT_PATTERN.sub("-", (value or "").strip()).strip("-._")
    return (normalized or default)[:120]


def _normalize_extension(extension: str | None, content_type: str | None) -> str:
    if extension:
        ext = extension.strip().lower().lstrip(".")
        if ext:
            return ext
    if content_type:
        guessed = mimetypes.guess_extension(content_type, strict=False)
        if guessed:
            return guessed.lstrip(".")
    return "bin"


@dataclass(slots=True, frozen=True)
class StoredArtifact:
    """Persisted artifact metadata returned by storage backends."""

    storage_path: str
    checksum: str
    size_bytes: int
    backend: str
    object_key: str
    bucket_name: str | None = None
    content_type: str | None = None


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
        extension: str | None = None,
        content_type: str | None = None,
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
            content_type="application/json",
        )

    async def get_temporary_download_url(self, *, storage_path: str, object_key: str | None, expires_in_seconds: int) -> str:
        """Return a temporary/non-public retrieval URL for this backend."""

        return storage_path

    async def check_health(self) -> tuple[bool, str]:
        """Validate backend is writable/reachable for readiness checks."""
        return True, "ok"

    def build_object_key(
        self,
        *,
        tenant_id: str | None,
        attempt_id: str | None,
        attempt_step_id: str | None,
        artifact_type: str,
        extension: str | None,
        content_type: str | None,
    ) -> str:
        now = datetime.now(UTC)
        safe_tenant = _safe_segment(tenant_id, default="tenant-unknown")
        safe_attempt = _safe_segment(attempt_id, default="attempt-unknown")
        safe_step = _safe_segment(attempt_step_id, default="step-global")
        safe_type = _safe_segment(artifact_type, default="artifact")
        safe_ext = _normalize_extension(extension, content_type)
        return (
            f"tenant={safe_tenant}/year={now:%Y}/month={now:%m}/day={now:%d}/"
            f"attempt={safe_attempt}/step={safe_step}/{safe_type}/"
            f"{now:%Y%m%dT%H%M%S%fZ}.{safe_ext}"
        )


class LocalArtifactStorage(ArtifactStorage):
    """Filesystem-backed storage for local development and test environments."""

    backend_name = "local"

    def __init__(self, root_dir: str) -> None:
        self._root = Path(root_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    async def check_health(self) -> tuple[bool, str]:
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            probe = self._root / ".healthcheck"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return True, "ok"
        except Exception as exc:  # noqa: BLE001
            return False, f"local_storage_unavailable:{exc}"

    async def store_bytes(
        self,
        *,
        tenant_id: str | None,
        attempt_id: str | None,
        attempt_step_id: str | None,
        artifact_type: str,
        payload: bytes,
        extension: str | None = None,
        content_type: str | None = None,
    ) -> StoredArtifact:
        if tenant_id:
            async with async_session_factory() as db:
                await control_plane.enforce_quota(
                    db,
                    tenant_id=tenant_id,
                    quota_key="artifact_storage_bytes",
                    increment=float(len(payload)),
                    context={"operation": "artifact_store", "backend": self.backend_name, "artifact_type": artifact_type},
                )
        object_key = self.build_object_key(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            attempt_step_id=attempt_step_id,
            artifact_type=artifact_type,
            extension=extension,
            content_type=content_type,
        )
        file_path = self._root / object_key
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(payload)

        checksum = hashlib.sha256(payload).hexdigest()
        size_bytes = len(payload)
        stored = StoredArtifact(
            storage_path=file_path.as_posix(),
            checksum=checksum,
            size_bytes=size_bytes,
            backend=self.backend_name,
            object_key=object_key,
            content_type=content_type,
        )
        artifact_storage_bytes_total.labels(backend=self.backend_name, artifact_type=artifact_type).inc(stored.size_bytes)
        return stored


class S3ArtifactStorage(ArtifactStorage):
    """S3-compatible object storage backend for durable artifact retention."""

    backend_name = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        endpoint_url: str | None,
        access_key_id: str,
        secret_access_key: str,
        session_token: str | None,
    ) -> None:
        self._bucket = bucket
        self._region = region
        self._endpoint_url = endpoint_url
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._session_token = session_token
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import boto3
        except Exception as exc:  # pragma: no cover - import behavior varies by env
            raise RuntimeError("boto3_required_for_s3_artifact_storage") from exc
        self._client = boto3.client(
            "s3",
            region_name=self._region,
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key_id,
            aws_secret_access_key=self._secret_access_key,
            aws_session_token=self._session_token,
        )
        return self._client

    async def store_bytes(
        self,
        *,
        tenant_id: str | None,
        attempt_id: str | None,
        attempt_step_id: str | None,
        artifact_type: str,
        payload: bytes,
        extension: str | None = None,
        content_type: str | None = None,
    ) -> StoredArtifact:
        if tenant_id:
            async with async_session_factory() as db:
                await control_plane.enforce_quota(
                    db,
                    tenant_id=tenant_id,
                    quota_key="artifact_storage_bytes",
                    increment=float(len(payload)),
                    context={"operation": "artifact_store", "backend": self.backend_name, "artifact_type": artifact_type},
                )
        object_key = self.build_object_key(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            attempt_step_id=attempt_step_id,
            artifact_type=artifact_type,
            extension=extension,
            content_type=content_type,
        )
        checksum = hashlib.sha256(payload).hexdigest()
        client = self._get_client()
        put_kwargs: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": object_key,
            "Body": payload,
            "Metadata": {
                "sha256": checksum,
                "artifact_type": _safe_segment(artifact_type, default="artifact"),
            },
        }
        if content_type:
            put_kwargs["ContentType"] = content_type
        client.put_object(**put_kwargs)

        stored = StoredArtifact(
            storage_path=f"s3://{self._bucket}/{object_key}",
            checksum=checksum,
            size_bytes=len(payload),
            backend=self.backend_name,
            object_key=object_key,
            bucket_name=self._bucket,
            content_type=content_type,
        )
        artifact_storage_bytes_total.labels(backend=self.backend_name, artifact_type=artifact_type).inc(stored.size_bytes)
        return stored

    async def get_temporary_download_url(self, *, storage_path: str, object_key: str | None, expires_in_seconds: int) -> str:
        key = object_key
        if not key:
            prefix = f"s3://{self._bucket}/"
            if not storage_path.startswith(prefix):
                raise ValueError("invalid_s3_storage_path")
            key = storage_path.removeprefix(prefix)
        client = self._get_client()
        return str(
            client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_in_seconds,
            ),
        )

    async def check_health(self) -> tuple[bool, str]:
        try:
            client = self._get_client()
            client.head_bucket(Bucket=self._bucket)
            return True, "ok"
        except Exception as exc:  # noqa: BLE001
            return False, f"s3_unreachable:{exc}"


def get_artifact_storage() -> ArtifactStorage:
    """Return configured storage backend."""

    settings = get_settings()
    provider = settings.artifact_storage_provider.lower()
    if provider == "local":
        return LocalArtifactStorage(settings.artifact_storage_local_root)
    if provider == "s3":
        return S3ArtifactStorage(
            bucket=settings.artifact_storage_s3_bucket,
            region=settings.artifact_storage_s3_region,
            endpoint_url=settings.artifact_storage_s3_endpoint_url or None,
            access_key_id=settings.artifact_storage_s3_access_key_id.get_secret_value(),
            secret_access_key=settings.artifact_storage_s3_secret_access_key.get_secret_value(),
            session_token=settings.artifact_storage_s3_session_token.get_secret_value() or None,
        )
    raise ValueError(f"Unsupported artifact storage provider: {provider}")
