import os
import boto3
import requests
from botocore.exceptions import BotoCoreError, NoCredentialsError, ClientError

def upload_file_with_fallback(file_path, file_name):
    print(f"[Storage] Upload requested for {file_name} ({file_path})")

    # --- AWS S3 ---
    try:
        print("[Storage] Trying AWS S3 upload...")
        s3 = boto3.client(
            "s3",
            aws_access_key_id=os.getenv("AWS_ACC_KEY"),
            aws_secret_access_key=os.getenv("AWS_SEC_KEY"),
            region_name=os.getenv("AWS_REGION", "us-east-1"),
        )
        bucket = os.getenv("AWS_S3_BUCKET")
        print(f"[Storage] AWS Bucket: {bucket}")

        s3.upload_file(file_path, bucket, file_name)
        s3_url = f"https://{bucket}.s3.{os.getenv('AWS_REGION', 'us-east-1')}.amazonaws.com/{file_name}"
        print(f"[✅ AWS] Uploaded successfully: {s3_url}")
        return s3_url
    except Exception as e:
        print(f"[❌ AWS] Upload failed: {type(e).__name__} - {e}")

    # --- Backblaze ---
    try:
        print("[Storage] Trying Backblaze upload...")
        import b2sdk.v2 as b2
        info = b2.InMemoryAccountInfo()
        b2_api = b2.B2Api(info)
        b2_api.authorize_account(
            "production",
            os.getenv("B2_KEY_ID"),
            os.getenv("B2_APPLICATION_KEY"),
        )
        bucket_name = os.getenv("B2_BUCKET_NAME")
        print(f"[Storage] Backblaze Bucket: {bucket_name}")
        bucket = b2_api.get_bucket_by_name(bucket_name)
        bucket.upload_local_file(local_file=file_path, file_name=file_name)
        b2_url = f"https://f002.backblazeb2.com/file/{bucket_name}/{file_name}"
        print(f"[✅ B2] Uploaded successfully: {b2_url}")
        return b2_url
    except Exception as e:
        print(f"[❌ Backblaze] Upload failed: {type(e).__name__} - {e}")

    # --- Local fallback ---
    try:
        print("[Storage] Falling back to local storage...")
        local_folder = os.path.join(os.getcwd(), "uploads_fallback")
        os.makedirs(local_folder, exist_ok=True)
        dest_path = os.path.join(local_folder, file_name)
        with open(file_path, "rb") as src, open(dest_path, "wb") as dst:
            dst.write(src.read())
        print(f"[✅ Local] File saved locally at {dest_path}")
        return dest_path
    except Exception as e:
        print(f"[❌ Local] Upload failed: {type(e).__name__} - {e}")

    raise RuntimeError("All storage methods failed")
