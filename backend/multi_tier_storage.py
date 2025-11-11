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

# --- Local fallback ---
LOCAL_UPLOAD_DIR = os.getenv("LOCAL_UPLOAD_DIR", "uploads")

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ================================
# STORAGE HANDLER FUNCTION
# ================================
def upload_file_with_fallback(file_path: str, file_name: str):
    """
    Upload a file to AWS S3 (primary). If that fails, try Backblaze B2.
    If that fails, store locally. Returns a dict with storage type and URL/path.
    """

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
    try:
        logger.info(
            f"[Storage] Attempting upload to Backblaze B2 bucket '{B2_BUCKET_NAME}'..."
        )

        # Step 1: Authorize
        auth_res = requests.get(
            "https://api.backblazeb2.com/b2api/v2/b2_authorize_account",
            auth=(B2_KEY_ID, B2_APPLICATION_KEY),
            timeout=10,
        )
        auth_res.raise_for_status()
        auth_data = auth_res.json()

        api_url = auth_data["apiUrl"]
        token = auth_data["authorizationToken"]

        # Step 2: Get bucket ID (handle restricted keys)
        bucket_id = auth_data["allowed"].get("bucketId")
        if not bucket_id:
            bucket_list = requests.post(
                f"{api_url}/b2api/v2/b2_list_buckets",
                headers={"Authorization": token},
                json={"accountId": auth_data["accountId"]},
                timeout=10,
            )
            bucket_list.raise_for_status()
            buckets = bucket_list.json().get("buckets", [])
            for b in buckets:
                if b["bucketName"] == B2_BUCKET_NAME:
                    bucket_id = b["bucketId"]
                    break
        if not bucket_id:
            raise RuntimeError(
                f"Could not resolve Backblaze bucket ID for {B2_BUCKET_NAME}"
            )

        # Step 3: Get upload URL
        upload_url_res = requests.post(
            f"{api_url}/b2api/v2/b2_get_upload_url",
            headers={"Authorization": token},
            json={"bucketId": bucket_id},
            timeout=10,
        )
        upload_url_res.raise_for_status()
        upload_data = upload_url_res.json()

        # Step 4: Upload file
        content_type, _ = mimetypes.guess_type(file_name)
        with open(file_path, "rb") as f:
            upload_res = requests.post(
                upload_data["uploadUrl"],
                headers={
                    "Authorization": upload_data["authorizationToken"],
                    "X-Bz-File-Name": file_name.replace(" ", "_"),
                    "Content-Type": content_type or "b2/x-auto",
                    "X-Bz-Content-Sha1": "do_not_verify",  # skip SHA1 to avoid CPU cost
                },
                data=f,
                timeout=30,
            )
        upload_res.raise_for_status()

        b2_url = f"{auth_data['downloadUrl']}/file/{B2_BUCKET_NAME}/{file_name.replace(' ', '_')}"
        logger.info(f"[Storage] Uploaded to Backblaze B2: {b2_url}")
        return {"storage": "backblaze", "url": b2_url}

    except Exception as e:
        logger.warning(f"[Storage] Backblaze B2 upload failed: {e}")
        logger.debug(traceback.format_exc())

    # --- Local Fallback ---
    try:
        logger.info("[Storage] Falling back to local storage...")
        os.makedirs(LOCAL_UPLOAD_DIR, exist_ok=True)
        local_path = Path(LOCAL_UPLOAD_DIR) / file_name
        shutil.copy2(file_path, local_path)  # safer than replace()
        logger.info(f"[Storage] Saved locally: {local_path}")
        return {"storage": "local", "path": str(local_path)}

    except Exception as e:
        logger.error(f"[Storage] Local save failed: {e}")
        logger.debug(traceback.format_exc())
        raise RuntimeError("All storage methods failed") from e
