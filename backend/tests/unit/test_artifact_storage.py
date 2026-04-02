"""Tests for artifact storage abstraction."""

from pathlib import Path

from app.services.artifacts.storage import LocalArtifactStorage, S3ArtifactStorage


class TestLocalArtifactStorage:
    async def test_store_json_writes_file_and_checksum(self, tmp_path: Path):
        storage = LocalArtifactStorage(str(tmp_path / "artifacts"))

        stored = await storage.store_json(
            tenant_id="tenant-1",
            application_id="application-1",
            attempt_id="attempt-1",
            attempt_step_id="step-1",
            artifact_type="verification_evidence",
            payload={"current_url": "https://example.com/confirmation", "submitted": True},
        )

        file_path = Path(stored.storage_path)
        assert stored.backend == "local"
        assert stored.size_bytes > 0
        assert stored.object_key
        assert file_path.exists()
        assert "tenant_id=tenant-1" in stored.storage_path


class _FakeS3Client:
    def __init__(self):
        self.put_calls = []

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)

    def generate_presigned_url(self, ClientMethod: str, Params: dict, ExpiresIn: int):
        return f"https://signed.example/{Params['Bucket']}/{Params['Key']}?expires={ExpiresIn}"


class TestS3ArtifactStorage:
    async def test_store_and_presign_roundtrip(self):
        storage = S3ArtifactStorage(
            bucket="artifact-bucket",
            region="us-east-1",
            endpoint_url="https://s3.example",
            access_key_id="key",
            secret_access_key="secret",
            session_token=None,
        )
        fake_client = _FakeS3Client()
        storage._client = fake_client  # noqa: SLF001

        stored = await storage.store_bytes(
            tenant_id="tenant-a",
            application_id="application-b",
            attempt_id="attempt-b",
            attempt_step_id="step-c",
            artifact_type="screenshot",
            payload=b"png-bytes",
            extension="png",
            content_type="image/png",
        )

        assert stored.storage_path.startswith("s3://artifact-bucket/")
        assert stored.backend == "s3"
        assert stored.bucket_name == "artifact-bucket"
        assert stored.content_type == "image/png"
        assert fake_client.put_calls

        signed = await storage.get_temporary_download_url(
            storage_path=stored.storage_path,
            object_key=stored.object_key,
            expires_in_seconds=600,
        )
        assert "https://signed.example/artifact-bucket/" in signed
