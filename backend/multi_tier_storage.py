import os
import boto3
import requests
from botocore.exceptions import BotoCoreError, ClientError
from datetime import datetime
from pathlib import Path

# ================================
# STORAGE CONFIGURATION
# ================================

# --- AWS S3 (Primary) ---
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET")
AWS_ACC_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SEC_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# --- Backblaze B2 (Secondary) ---
B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME")
B2_KEY_ID = os.getenv("B2_KEY_ID")
B2_APPLICATION_KEY = os.getenv("B2_APPLICATION_KEY")

# --- Local fallback ---
LOCAL_UPLOAD_DIR = os.getenv("LOCAL_UPLOAD_DIR", "uploads")


# ================================
# STORAGE HANDLER FUNCTION
# ================================
def upload_file_with_fallback(file_path: str, file_name: str):
    """
    Attempts to upload a file to S3.
    Falls back to Backblaze B2 if S3 fails,
    and finally stores locally if both fail.
    Returns the URL or path of the uploaded file.
    """

    # ---------- 1️⃣ Try AWS S3 ----------
    try:
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=AWS_ACC_KEY,
            aws_secret_access_key=AWS_SEC_KEY,
            region_name=AWS_REGION,
        )

        s3_client.upload_file(file_path, AWS_S3_BUCKET, file_name)
        s3_url = f"https://{AWS_S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{file_name}"
        print(f"[Storage] Uploaded to S3: {s3_url}")
        return {"storage": "s3", "url": s3_url}

    except (BotoCoreError, ClientError) as e:
        print(f"[Storage] S3 upload failed: {e}")
    # ---------- 2️⃣ Try Backblaze B2 ----------
    try:
        # Authorize
        auth_res = requests.get(
            "https://api.backblazeb2.com/b2api/v2/b2_authorize_account",
            auth=(B2_KEY_ID, B2_APPLICATION_KEY),
        )
        auth_res.raise_for_status()
        auth_data = auth_res.json()
        api_url = auth_data["apiUrl"]
        token = auth_data["authorizationToken"]

        # Get upload URL
        bucket_res = requests.post(
            f"{api_url}/b2api/v2/b2_get_upload_url",
            headers={"Authorization": token},
            json={"bucketId": auth_data["allowed"]["bucketId"]},
        )
        bucket_res.raise_for_status()
        upload_data = bucket_res.json()

        # Upload file
        with open(file_path, "rb") as f:
            upload_res = requests.post(
                upload_data["uploadUrl"],
                headers={
                    "Authorization": upload_data["authorizationToken"],
                    "X-Bz-File-Name": file_name,
                    "Content-Type": "b2/x-auto",
                },
                data=f,
            )
        upload_res.raise_for_status()
        b2_url = f"{auth_data['downloadUrl']}/file/{B2_BUCKET_NAME}/{file_name}"
        print(f"[Storage] Uploaded to Backblaze B2: {b2_url}")
        return {"storage": "backblaze", "url": b2_url}

    except Exception as e:
        print(f"[Storage] ⚠️ Backblaze upload failed: {e}")

   
    # ---------- 3️⃣ Local Fallback ----------
    try:
        os.makedirs(LOCAL_UPLOAD_DIR, exist_ok=True)
        local_path = Path(LOCAL_UPLOAD_DIR) / file_name
        Path(file_path).replace(local_path)
        print(f"[Storage] Saved locally: {local_path}")
        return {"storage": "local", "path": str(local_path)}

    except Exception as e:
        print(f"[Storage] Local save failed: {e}")
        raise RuntimeError("All storage methods failed") from e
