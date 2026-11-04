
import os
from datetime import timezone
from pathlib import PurePosixPath
from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "intraq-automations")


@lru_cache(maxsize=1)
def get_r2_client():
    """Create and reuse a Cloudflare R2 S3-compatible client."""
    account_id = os.getenv("R2_ACCOUNT_ID")
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")

    if not all([account_id, access_key, secret_key]):
        raise RuntimeError(
            "Missing R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, "
            "or R2_SECRET_ACCESS_KEY environment variables."
        )

    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def _normalize_segment(value: str, field_name: str) -> str:
    """Normalize one client/project identifier and reject unsafe paths."""
    value = str(value or "").strip().lower().replace("_", "-")

    if (
        not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\x00" in value
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}.",
        )

    return value


def _user_prefix(client_id: str) -> str:
    client_id = _normalize_segment(client_id, "client_id")
    return f"user-{client_id}/"


def _project_prefix(client_id: str, project_code: str) -> str:
    project_code = _normalize_segment(project_code, "project_code")
    return f"{_user_prefix(client_id)}{project_code}/"


def _ensure_bucket_exists():
    """Check that the configured R2 bucket exists and is accessible."""
    try:
        get_r2_client().head_bucket(Bucket=BUCKET_NAME)
    except ClientError as exc:
        print(f"R2 bucket check failed: {exc}")
        raise HTTPException(
            status_code=503,
            detail="R2 bucket is unavailable or inaccessible.",
        ) from exc
    except BotoCoreError as exc:
        print(f"R2 connection failed: {exc}")
        raise HTTPException(
            status_code=503,
            detail="Unable to connect to R2.",
        ) from exc


def _create_folder_marker(prefix: str):
    """Create an optional zero-byte object representing a folder."""
    get_r2_client().put_object(
        Bucket=BUCKET_NAME,
        Key=prefix,
        Body=b"",
        ContentType="application/x-directory",
    )


def create_user_r2_structure(client_id: str):
    """
    Legacy function name retained for compatibility.
    Initialize a user's prefix in the shared R2 bucket.
    """
    try:
        prefix = _user_prefix(client_id)
        _ensure_bucket_exists()
        _create_folder_marker(prefix)
        return BUCKET_NAME

    except HTTPException:
        raise
    except (ClientError, BotoCoreError) as exc:
        print(f"R2 error creating user structure: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create R2 user storage structure.",
        ) from exc


def create_project_r2_structure(
    client_id: str,
    project_code: str,
    normalized_count: int = 10,
):
    """
    Legacy function name retained for compatibility.
    Initialize project folder markers in the shared R2 bucket.
    """
    if not client_id:
        raise HTTPException(status_code=400, detail="Missing client_id.")

    if not project_code:
        raise HTTPException(status_code=400, detail="Missing project_code.")

    try:
        normalized_count = int(normalized_count)

        if not 0 <= normalized_count <= 100:
            raise HTTPException(
                status_code=400,
                detail="normalized_count must be between 0 and 100.",
            )

        project_prefix = _project_prefix(client_id, project_code)
        _ensure_bucket_exists()

        subfolders = [
            f"{project_prefix}uploads/",
            f"{project_prefix}pipelines/",
            f"{project_prefix}progress/",
            f"{project_prefix}automations/",
            f"{project_prefix}base_files/",
            f"{project_prefix}normalized_base/",
            f"{project_prefix}processed/",
            f"{project_prefix}logs/",
        ]

        subfolders.extend(
            f"{project_prefix}normalized{i}/"
            for i in range(1, normalized_count + 1)
        )

        client = get_r2_client()

        # Use one client and create markers for the requested prefixes.
        for prefix in subfolders:
            client.put_object(
                Bucket=BUCKET_NAME,
                Key=prefix,
                Body=b"",
                ContentType="application/x-directory",
            )

        return BUCKET_NAME

    except HTTPException:
        raise
    except (ClientError, BotoCoreError) as exc:
        print(f"R2 error creating project structure: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create R2 project storage structure.",
        ) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail="normalized_count must be an integer.",
        ) from exc

def get_directory_tree(client_id: str, project_code: str):
    """
    Return the project's directory tree from Cloudflare R2
    for frontend display.
    """
    prefix = get_project_bucket_folder(client_id, project_code)

    if not prefix:
        return None

    return fetch_directory_data(prefix)


def fetch_directory_data(path: str):
    """
    List objects under an R2 prefix and build a nested directory tree.

    `path` is an R2 object-key prefix, not a local filesystem path.

    Folders are inferred from object keys. Explicit zero-byte folder
    markers are also supported.

    Returns folders first, then files, alphabetically within each group.
    """
    client = get_r2_client()
    prefix = str(path).strip("/")

    if prefix:
        prefix += "/"

    items = {}
    continuation_token = None

    try:
        # Delimiter groups direct children into CommonPrefixes.
        # Pagination is necessary for directories with many objects.
        while True:
            params = {
                "Bucket": BUCKET_NAME,
                "Prefix": prefix,
                "Delimiter": "/",
                "MaxKeys": 1000,
            }

            if continuation_token:
                params["ContinuationToken"] = continuation_token

            response = client.list_objects_v2(**params)

            # Directories represented by R2 object-key prefixes.
            for entry in response.get("CommonPrefixes", []):
                folder_prefix = entry["Prefix"]
                folder_name = folder_prefix[len(prefix):].rstrip("/")

                if not folder_name:
                    continue

                items[folder_name] = {
                    "name": folder_name,
                    "path": folder_name,
                    "type": "folder",
                    "size": None,
                    "modified_at": None,
                    "children": fetch_directory_data(folder_prefix),
                }

            # Files immediately inside the requested prefix.
            for obj in response.get("Contents", []):
                key = obj["Key"]
                relative_key = key[len(prefix):]

                if not relative_key:
                    continue

                # Ignore explicit directory marker objects. The folder
                # is already represented by its CommonPrefix.
                if relative_key.endswith("/") and obj.get("Size", 0) == 0:
                    continue

                # Delimiter="/" should return direct files here.
                # Guard against nested keys in case of unusual responses.
                if "/" in relative_key:
                    continue

                modified = obj.get("LastModified")

                items[relative_key] = {
                    "name": relative_key,
                    "path": relative_key,
                    "type": "file",
                    "size": obj.get("Size", 0),
                    "modified_at": (
                        modified.isoformat() if modified else None
                    ),
                }

            if not response.get("IsTruncated"):
                break

            continuation_token = response.get("NextContinuationToken")

        # Match the original ordering: folders first, files second.
        return sorted(
            items.values(),
            key=lambda item: (
                item["type"] == "file",
                item["name"].lower(),
            ),
        )

    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        print(f"R2 listing error for prefix {prefix}: {exc}")

        if error_code in {"AccessDenied", "Forbidden"}:
            raise HTTPException(
                status_code=403,
                detail="Permission denied while listing R2 objects.",
            ) from exc

        raise HTTPException(
            status_code=500,
            detail="Failed to list R2 directory contents.",
        ) from exc

    except BotoCoreError as exc:
        print(f"R2 connection error for prefix {prefix}: {exc}")
        raise HTTPException(
            status_code=503,
            detail="Unable to connect to R2.",
        ) from exc
