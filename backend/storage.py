"""Storage backend scaffold with switchable implementations.

This module introduces a lightweight interface that can be used throughout
the backend to abstract away whether files live on the local filesystem or
in an object store such as AWS S3 or Cloudflare R2.  The goal is to keep
existing call-sites decoupled from storage-specific details, so swapping
implementations only requires reconfiguring the storage driver.
"""

from __future__ import annotations

import io
import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Dict, Iterable, Optional


# ---------------------------------------------------------------------------
# Storage interface
# ---------------------------------------------------------------------------


@dataclass
class StorageObject:
    """Small metadata container returned by storage backends."""

    key: str
    size: Optional[int] = None
    modified_at: Optional[float] = None
    extra: Optional[dict] = None


class StorageBackend(ABC):
    """Minimal set of operations needed by the backend."""

    @abstractmethod
    def save_file(self, key: str, source_path: Path) -> StorageObject:
        ...

    @abstractmethod
    def save_bytes(self, key: str, data: bytes) -> StorageObject:
        ...

    @abstractmethod
    def open_binary(self, key: str) -> BinaryIO:
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        ...

    @abstractmethod
    def list(self, prefix: str = "") -> Iterable[StorageObject]:
        ...


# ---------------------------------------------------------------------------
# Local filesystem backend (default)
# ---------------------------------------------------------------------------


class LocalFileStorage(StorageBackend):
    """Existing behaviour: store files inside a local root folder."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        return self.root / key

    def save_file(self, key: str, source_path: Path) -> StorageObject:
        destination = self._resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(Path(source_path).read_bytes())
        stat = destination.stat()
        return StorageObject(key=key, size=stat.st_size, modified_at=stat.st_mtime)

    def save_bytes(self, key: str, data: bytes) -> StorageObject:
        destination = self._resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        stat = destination.stat()
        return StorageObject(key=key, size=stat.st_size, modified_at=stat.st_mtime)

    def open_binary(self, key: str) -> BinaryIO:
        return self._resolve(key).open("rb")

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.exists():
            path.unlink()

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    def list(self, prefix: str = "") -> Iterable[StorageObject]:
        base = self._resolve(prefix)
        if base.is_file():
            stat = base.stat()
            yield StorageObject(key=prefix, size=stat.st_size, modified_at=stat.st_mtime)
            return

        if not base.exists():
            return

        for path in base.rglob("*"):
            if path.is_file():
                stat = path.stat()
                relative_key = path.relative_to(self.root).as_posix()
                yield StorageObject(
                    key=relative_key, size=stat.st_size, modified_at=stat.st_mtime
                )


# ---------------------------------------------------------------------------
# Mock S3-compatible backend
# ---------------------------------------------------------------------------


class MockS3Storage(StorageBackend):
    """In-memory stand-in for S3/R2 used for local development and testing."""

    def __init__(self, bucket: str, endpoint_url: Optional[str] = None):
        self.bucket = bucket
        self.endpoint_url = endpoint_url or "https://mock-s3.local"
        self._objects: Dict[str, bytes] = {}
        self._lock = threading.Lock()

    def _touch(self, key: str, data: bytes) -> StorageObject:
        meta = StorageObject(
            key=key, size=len(data), modified_at=time.time(), extra={"bucket": self.bucket}
        )
        return meta

    def save_file(self, key: str, source_path: Path) -> StorageObject:
        return self.save_bytes(key, Path(source_path).read_bytes())

    def save_bytes(self, key: str, data: bytes) -> StorageObject:
        with self._lock:
            self._objects[key] = bytes(data)
            return self._touch(key, data)

    def open_binary(self, key: str) -> BinaryIO:
        with self._lock:
            if key not in self._objects:
                raise FileNotFoundError(f"{key} not found in mock bucket {self.bucket}")
            return io.BytesIO(self._objects[key])

    def delete(self, key: str) -> None:
        with self._lock:
            self._objects.pop(key, None)

    def exists(self, key: str) -> bool:
        with self._lock:
            return key in self._objects

    def list(self, prefix: str = "") -> Iterable[StorageObject]:
        with self._lock:
            for key, value in self._objects.items():
                if not prefix or key.startswith(prefix):
                    yield self._touch(key, value)


# ---------------------------------------------------------------------------
# Switcher / configuration helpers
# ---------------------------------------------------------------------------


@dataclass
class StorageConfig:
    driver: str = "local"
    local_root: Path = Path("uploads")
    bucket: str = "mock-bucket"
    endpoint_url: Optional[str] = None

    @classmethod
    def from_env(cls) -> "StorageConfig":
        return cls(
            driver=os.getenv("STORAGE_DRIVER", "local"),
            local_root=Path(os.getenv("STORAGE_LOCAL_ROOT", "uploads")),
            bucket=os.getenv("STORAGE_BUCKET", "mock-bucket"),
            endpoint_url=os.getenv("STORAGE_ENDPOINT_URL"),
        )


_storage_backend: Optional[StorageBackend] = None


def configure_storage(config: Optional[StorageConfig] = None) -> StorageBackend:
    """Instantiate and cache the desired backend implementation."""
    global _storage_backend
    config = config or StorageConfig.from_env()
    driver = config.driver.lower()

    if driver == "local":
        backend = LocalFileStorage(config.local_root)
    elif driver in {"mock_s3", "s3"}:
        backend = MockS3Storage(bucket=config.bucket, endpoint_url=config.endpoint_url)
    else:
        raise ValueError(f"Unsupported storage driver '{config.driver}'")

    _storage_backend = backend
    return backend


def get_storage() -> StorageBackend:
    """Return the configured storage backend (initialising if needed)."""
    global _storage_backend
    if _storage_backend is None:
        configure_storage()
    return _storage_backend

