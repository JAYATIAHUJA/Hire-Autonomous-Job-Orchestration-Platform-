"""Object storage for uploaded files. S3 API only (ADR-009): SeaweedFS in dev, AWS S3 in prod."""

from typing import Optional, Protocol

from fastapi import HTTPException

from ..config import settings


class ObjectStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class S3ObjectStore:
    def __init__(self) -> None:
        import boto3  # imported lazily so tests and S3-less runs don't pay for it

        self._bucket = settings.s3_bucket
        self._s3 = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint or None,
            aws_access_key_id=settings.s3_access_key or None,
            aws_secret_access_key=settings.s3_secret_key or None,
            region_name=settings.s3_region,
        )

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        return self._s3.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        # S3 DeleteObject succeeds for a missing key, so erasure is idempotent.
        self._s3.delete_object(Bucket=self._bucket, Key=key)


class InMemoryObjectStore:
    """For tests and local experiments."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    def get(self, key: str) -> bytes:
        return self.objects[key][0]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


_store: Optional[ObjectStore] = None


def get_object_store() -> Optional[ObjectStore]:
    """FastAPI dependency; None until S3_BUCKET is configured. Tests override it.

    Returning None (rather than raising) lets erasure still run on an account that never
    stored a file; routes that need storage call ``require_store``.
    """
    global _store
    if _store is None and settings.s3_bucket:
        _store = S3ObjectStore()
    return _store


def require_store(store: Optional[ObjectStore]) -> ObjectStore:
    if store is None:
        raise HTTPException(status_code=503, detail="File storage is not configured (S3_BUCKET).")
    return store
