import os
import re
import time
import boto3
import requests
import logging
import mimetypes
import shutil
import threading
import traceback
import tempfile
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import quote
from datetime import datetime
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError

# ================================
# CONFIGURATION
# ================================

# --- AWS S3 (Primary) ---
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET")
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("AWS_ACC_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY") or os.getenv("AWS_SEC_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# --- Backblaze B2 (Secondary) ---
B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME")
B2_KEY_ID = os.getenv("B2_KEY_ID")
B2_APPLICATION_KEY = os.getenv("B2_APPLICATION_KEY")
B2_AUTH_TTL = int(os.getenv("B2_AUTH_TTL", "3600"))

# --- Local fallback ---
LOCAL_UPLOAD_DIR = os.getenv("LOCAL_UPLOAD_DIR") or str(
    Path(tempfile.gettempdir()) / "doca11y_uploads"
)

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

_B2_AUTH_CACHE: dict = {}
_B2_AUTH_LOCK = threading.Lock()


# ================================
# STORAGE HANDLER FUNCTION
# ================================
def upload_file_with_fallback(
    file_path: str, file_name: str, folder: Optional[str] = None
):
    """
    Upload a file to AWS S3 (primary). If that fails, try Backblaze B2.
    If that fails, store locally. Returns a dict with storage type and URL/path.
    """
    storage_key = _build_storage_key(file_name, folder)

    # # --- Try AWS S3 ---
    # try:
    #     logger.info(f"[Storage] Uploading '{file_name}' to AWS S3...")
    #     s3_client = boto3.client(
    #         "s3",
    #         aws_access_key_id=AWS_ACCESS_KEY,
    #         aws_secret_access_key=AWS_SECRET_KEY,
    #         region_name=AWS_REGION,
    #         config=Config(retries={"max_attempts": 3}),
    #     )

    #     content_type, _ = mimetypes.guess_type(file_name)
    #     extra_args = {"ContentType": content_type or "application/octet-stream"}

    #     s3_client.upload_file(file_path, AWS_S3_BUCKET, file_name, ExtraArgs=extra_args)
    #     s3_url = f"https://{AWS_S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{file_name}"
    #     logger.info(f"[Storage] Uploaded to S3: {s3_url}")
    #     return {"storage": "s3", "url": s3_url}

    # except (BotoCoreError, ClientError, EndpointConnectionError) as e:
    #     logger.warning(f"[Storage] S3 upload failed: {e}")
    #     logger.debug(traceback.format_exc())

    # --- Try Backblaze B2 ---
    if has_backblaze_storage():
        try:
            logger.info(
                "[Storage] Attempting upload to Backblaze B2 bucket '%s' (key=%s)",
                B2_BUCKET_NAME,
                storage_key,
            )
            auth = _get_b2_authorization()
            upload_data = _get_b2_upload_url(auth)
            content_type, _ = mimetypes.guess_type(file_name)
            with open(file_path, "rb") as f:
                upload_res = requests.post(
                    upload_data["uploadUrl"],
                    headers={
                        "Authorization": upload_data["authorizationToken"],
                        "X-Bz-File-Name": _encode_b2_file_name(storage_key),
                        "Content-Type": content_type or "b2/x-auto",
                        "X-Bz-Content-Sha1": "do_not_verify",
                    },
                    data=f,
                    timeout=60,
                )
            upload_res.raise_for_status()
            b2_url = _build_backblaze_file_url(storage_key, auth)
            logger.info("[Storage] Uploaded to Backblaze B2: %s", b2_url)
            return {
                "storage": "backblaze",
                "url": b2_url,
                "key": storage_key,
                "path": storage_key,
            }
        except Exception as e:
            logger.warning(f"[Storage] Backblaze B2 upload failed: {e}")
            logger.debug(traceback.format_exc())

    # --- Local Fallback ---
    try:
        logger.info("[Storage] Falling back to local storage for %s", storage_key)
        local_path = _local_destination_path(storage_key)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, local_path)
        logger.info(f"[Storage] Saved locally: {local_path}")
        return {"storage": "local", "path": str(local_path), "key": storage_key}

    except Exception as e:
        logger.error(f"[Storage] Local save failed: {e}")
        logger.debug(traceback.format_exc())
        raise RuntimeError("All storage methods failed") from e


def has_backblaze_storage() -> bool:
    return all([B2_BUCKET_NAME, B2_KEY_ID, B2_APPLICATION_KEY])


def stream_remote_file(identifier: str, chunk_size: int = 8192) -> Iterator[bytes]:
    """
    Stream bytes from a remote storage reference. Identifier can be a URL or
    a Backblaze key (e.g., 'uploads/file.pdf').
    """
    url = _resolve_remote_identifier(identifier)
    response = requests.get(url, stream=True, timeout=60)
    if response.status_code == 404:
        response.close()
        raise FileNotFoundError(identifier)
    response.raise_for_status()

    def _iterator():
        try:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    yield chunk
        finally:
            response.close()

    return _iterator()


def download_remote_file(
    identifier: str, destination: Path, chunk_size: int = 8192
) -> Path:
    """
    Download a remote file (URL or Backblaze key) to a local destination.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    stream = stream_remote_file(identifier, chunk_size=chunk_size)
    with open(destination, "wb") as target:
        for chunk in stream:
            target.write(chunk)
    return destination


def _build_storage_key(file_name: str, folder: Optional[str] = None) -> str:
    base = _sanitize_path_component(file_name) or f"file_{int(time.time())}"
    folder_component = _sanitize_path_component(folder) if folder else ""
    if folder_component:
        return f"{folder_component}/{base}"
    return base


def _local_destination_path(storage_key: str) -> Path:
    """
    Map a storage key (which may include a top-level folder like 'uploads/file.pdf')
    to a path under LOCAL_UPLOAD_DIR without duplicating the folder name.
    """
    local_root = Path(LOCAL_UPLOAD_DIR or ".")
    key_path = Path(storage_key)
    parts = list(key_path.parts)
    if parts and local_root.name == parts[0]:
        parts = parts[1:]
    relative = Path(*parts) if parts else Path(key_path.name)
    return local_root / relative


def _get_b2_authorization() -> dict:
    if not has_backblaze_storage():
        raise RuntimeError("Backblaze credentials are not fully configured")

    now = time.time()
    with _B2_AUTH_LOCK:
        if _B2_AUTH_CACHE and now < _B2_AUTH_CACHE.get("expires_at", 0):
            return _B2_AUTH_CACHE

        auth_res = requests.get(
            "https://api.backblazeb2.com/b2api/v2/b2_authorize_account",
            auth=(B2_KEY_ID, B2_APPLICATION_KEY),
            timeout=10,
        )
        auth_res.raise_for_status()
        auth_data = auth_res.json()

        bucket_id = auth_data["allowed"].get("bucketId")
        if not bucket_id:
            bucket_id = _lookup_bucket_id(
                auth_data["apiUrl"], auth_data["authorizationToken"], auth_data["accountId"]
            )
        if not bucket_id:
            raise RuntimeError(
                f"Could not resolve Backblaze bucket ID for {B2_BUCKET_NAME}"
            )

        auth_payload = {
            "apiUrl": auth_data["apiUrl"],
            "downloadUrl": auth_data["downloadUrl"],
            "authorizationToken": auth_data["authorizationToken"],
            "bucketId": bucket_id,
            "expires_at": now + B2_AUTH_TTL,
        }
        _B2_AUTH_CACHE.update(auth_payload)
        return auth_payload


def _lookup_bucket_id(api_url: str, token: str, account_id: str) -> Optional[str]:
    try:
        bucket_list = requests.post(
            f"{api_url}/b2api/v2/b2_list_buckets",
            headers={"Authorization": token},
            json={"accountId": account_id},
            timeout=10,
        )
        bucket_list.raise_for_status()
        buckets = bucket_list.json().get("buckets", [])
        for bucket in buckets:
            if bucket.get("bucketName") == B2_BUCKET_NAME:
                return bucket.get("bucketId")
    except Exception:
        logger.warning("Failed to list Backblaze buckets")
        logger.debug(traceback.format_exc())
    return None


def _get_b2_upload_url(auth: dict) -> dict:
    upload_url_res = requests.post(
        f"{auth['apiUrl']}/b2api/v2/b2_get_upload_url",
        headers={"Authorization": auth["authorizationToken"]},
        json={"bucketId": auth["bucketId"]},
        timeout=10,
    )
    upload_url_res.raise_for_status()
    return upload_url_res.json()


def _build_backblaze_file_url(storage_key: str, auth: Optional[dict] = None) -> str:
    auth_data = auth or _get_b2_authorization()
    encoded_key = _encode_b2_file_name(storage_key)
    return f"{auth_data['downloadUrl']}/file/{B2_BUCKET_NAME}/{encoded_key}"


def _encode_b2_file_name(storage_key: str) -> str:
    normalized = storage_key.strip("/").replace("\\", "/")
    return quote(normalized, safe="/._-")


def _resolve_remote_identifier(identifier: str) -> str:
    if identifier.lower().startswith(("http://", "https://")):
        return identifier
    if not has_backblaze_storage():
        raise RuntimeError(
            "Backblaze storage is not configured; cannot resolve remote identifier"
        )
    return _build_backblaze_file_url(identifier)


def _sanitize_path_component(value: Optional[str]) -> str:
    if not value:
        return ""
    value = value.replace("\\", "/").strip("/")
    return re.sub(r"[^A-Za-z0-9._/-]", "_", value)
