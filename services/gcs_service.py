
from google.cloud import storage
import os
from dotenv import load_dotenv


def get_gcs_client():
    """Get Google Cloud Storage client with proper credentials"""
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    
    if credentials_path:
        if os.path.exists(credentials_path):
            print(f"✅ Using service account key: {credentials_path}")
            return storage.Client.from_service_account_json(credentials_path)
        else:
            print(f"⚠️ Credentials file not found: {credentials_path}")
    
    # Fallback to Application Default Credentials
    print("Using Application Default Credentials")
    return storage.Client()        


def create_user_gcs_structure(client_id: str):
    
    try:
        storage_client = get_gcs_client()   # Uses default credentials (service account / ADC)

        # Option 1: Create a dedicated bucket per user (recommended for isolation)
        bucket_name = "intraq-automations"
        root_folder_name = f"user-{client_id.lower()}".replace("_", "-")
        # Bucket names must be globally unique and follow GCS rules (lowercase, no underscores)

        bucket = storage_client.bucket(bucket_name)
        
        if not bucket.exists():
            bucket = storage_client.create_bucket(bucket_name, location="US")  # or "EU", "ASIA", etc.
            print(f"Bucket {bucket_name} created successfully.")
        else:
            print(f"Bucket {bucket_name} already exists.")

        # Create subfolders (in GCS, folders are simulated by uploading a blob with trailing slash)
        subfolders = [
            f"{root_folder_name}/"
        ]

        for folder in subfolders:
            blob = bucket.blob(folder)
            blob.upload_from_string(
                '', 
                content_type='application/x-www-form-urlencoded;charset=UTF-8'
            )
            print(f"Subfolder created: {folder}")

        return bucket_name

    except Exception as e:
        print(f"GCS Error: {e}")
        # Don't fail signup just because GCS failed (make it non-blocking or handle gracefully)
        raise HTTPException(status_code=500, detail=f"Failed to create storage structure: {str(e)}")


def create_project_gcs_structure(client_id: str, project_code: str, normalized_count: str = 10):

	if not client_id:
		print(f"Missing client_id .")
		raise HTTPException(status_code=500, detail=f"Failed to create storage structure: Missing client_id.")

	if not project_code:
		print(f"Missing project_code.")
		raise HTTPException(status_code=500, detail=f"Failed to create storage structure: Missing project_code.")

    """Create GCS bucket + subfolders for the new user"""
    try:
        storage_client = get_gcs_client()   # Uses default credentials (service account / ADC)

        # Option 1: Create a dedicated bucket per user (recommended for isolation)
        bucket_name = "intraq-automations"
        root_folder_name = f"user-{client_id.lower()}".replace("_", "-")
        project_code = project_code.lower()
        # Bucket names must be globally unique and follow GCS rules (lowercase, no underscores)

        bucket = storage_client.bucket(bucket_name)
        
        if not bucket.exists():
            bucket = storage_client.create_bucket(bucket_name, location="US")  # or "EU", "ASIA", etc.
            print(f"Bucket {bucket_name} created successfully.")
        else:
            print(f"Bucket {bucket_name} already exists.")

        # Create subfolders (in GCS, folders are simulated by uploading a blob with trailing slash)
        subfolders = [
            f"{root_folder_name}/{project_code}/uploads/",
            f"{root_folder_name}/{project_code}/pipelines/",
            f"{root_folder_name}/{project_code}/progress/",
            f"{root_folder_name}/{project_code}/automations/",           # for your automation files
            f"{root_folder_name}/{project_code}/base_files/",
            f"{root_folder_name}/{project_code}/normalized_base/",
            f"{root_folder_name}/{project_code}/processed/",
            f"{root_folder_name}/{project_code}/logs/"
        ]

        for i in range(1,normalized_count+1):
        	subfolders.append(f"{root_folder_name}/{project_code}/normalized{i}/")

        for folder in subfolders:
            blob = bucket.blob(folder)
            blob.upload_from_string(
                '', 
                content_type='application/x-www-form-urlencoded;charset=UTF-8'
            )
            print(f"Subfolder created: {folder}")

        return bucket_name

    except Exception as e:
        print(f"GCS Error: {e}")
        # Don't fail signup just because GCS failed (make it non-blocking or handle gracefully)
        raise HTTPException(status_code=500, detail=f"Failed to create storage structure: {str(e)}")


