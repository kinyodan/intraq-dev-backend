"""
DFE Automation Service - Database-Centric Data Processing

This service integrates with the dataentry backend's database-centric architecture:
- Quick Clean: Synchronous cleaning before saving to database
- Enrichment: Asynchronous processing for heavy operations
- Works with PostgreSQL tables instead of file paths
- Tracks processing status in the Dataset model
"""

import os
import sys
import json
import logging
from datetime import datetime
from typing import Optional, Dict, List, Callable, Any
from pathlib import Path
import pandas as pd
import io

# Add DFE path to import the automation modules
DFE_PATH = os.path.expanduser("~/dev/dfe")
AUTOMATION_PATH = os.path.join(DFE_PATH, "automation")

if DFE_PATH not in sys.path:
    sys.path.insert(0, DFE_PATH)
if AUTOMATION_PATH not in sys.path:
    sys.path.insert(0, AUTOMATION_PATH)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dfe_automation")


class DataProcessingService:
    """
    Two-Phase Data Processing Service
    
    PHASE 1 - QUICK CLEAN (Synchronous):
    - Runs during upload, before saving to database
    - Fast operations (< 1 second per file)
    - Essential field validation and formatting
    
    PHASE 2 - ENRICHMENT (Asynchronous):
    - Runs as background job after upload completes
    - Heavy operations (GPS generation, file splitting)
    - Updates existing database records
    - Creates output files for downstream use
    """
    
    # Configuration
    LOG_FILE = os.path.expanduser("~/dev/dfe/dfe_service.log")
    OUTPUT_DIR = os.path.expanduser("~/dev/dfe/processed_output")
    
    # Track running enrichment jobs
    _active_jobs: Dict[str, Dict] = {}
    
    def __init__(self):
        """Initialize the service"""
        os.makedirs(self.OUTPUT_DIR, exist_ok=True)
        self._import_dfe_modules()
    
    def _import_dfe_modules(self):
        """Import DFE automation modules for enrichment phase"""
        self.dfe_modules = {}
        
        try:
            from automation.data_normalizer_v2 import (
                clean_name, clean_phone_number, clean_id_number,
                standardize_sex, parse_date_of_birth, calculate_age,
                normalize_caw, get_caw_coordinates, random_coordinate
            )
            from automation.csv_splitter_v2 import split_by_caw
            
            self.dfe_modules = {
                'clean_name': clean_name,
                'clean_phone_number': clean_phone_number,
                'clean_id_number': clean_id_number,
                'standardize_sex': standardize_sex,
                'parse_date_of_birth': parse_date_of_birth,
                'calculate_age': calculate_age,
                'normalize_caw': normalize_caw,
                'get_caw_coordinates': get_caw_coordinates,
                'random_coordinate': random_coordinate,
                'split_by_caw': split_by_caw
            }
            logger.info("DFE enrichment modules loaded successfully")
        except ImportError as e:
            logger.error(f"Failed to import DFE modules: {e}")
            self.dfe_modules = {}
    
    def _log(self, message: str, job_id: Optional[str] = None):
        """Log message to file and logger"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] {message}"
        logger.info(message)
        
        with open(self.LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_msg + "\n")
    
    # ==========================================================================
    # PHASE 1: QUICK CLEAN (Synchronous - runs during upload)
    # ==========================================================================
    
    def quick_clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Quick cleaning operations - runs synchronously before database save
        
        These operations are fast (< 1 second) and essential for data quality:
        - Name formatting
        - Phone number standardization
        - ID cleaning
        - Gender standardization
        - Date parsing and age calculation
        
        Args:
            df: Raw DataFrame from uploaded file
            
        Returns:
            Cleaned DataFrame ready for database insertion
        """
        if df.empty:
            return df
        
        logger.info(f"Starting quick clean on {len(df)} records")
        df = df.copy()
        
        # 1. Clean and create full names
        df = self._clean_names(df)
        
        # 2. Clean phone numbers
        df = self._clean_phones(df)
        
        # 3. Clean ID numbers
        df = self._clean_ids(df)
        
        # 4. Standardize gender
        df = self._clean_gender(df)
        
        # 5. Parse dates and calculate ages
        df = self._process_dates_and_ages(df)
        
        # 6. Basic location cleanup
        df = self._basic_location_cleanup(df)
        
        # 7. Add metadata columns
        df['_uploaded_at'] = datetime.utcnow()
        df['_cleaned'] = True
        
        logger.info(f"Quick clean complete. {len(df)} records ready")
        return df
    
    def _clean_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean name fields and create full_name"""
        name_cols = ['fname', 'mname', 'sname', 'first_name', 'middle_name', 'surname', 'last_name']
        
        # Find which columns exist
        existing_cols = [col for col in name_cols if col in df.columns]
        
        for col in existing_cols:
            df[col] = df[col].astype(str).str.strip().str.title()
            df[col] = df[col].replace(['Nan', 'None', ''], '')
        
        # Create full_name if we have first and last name columns
        first_col = next((c for c in ['fname', 'first_name'] if c in df.columns), None)
        last_col = next((c for c in ['sname', 'surname', 'last_name'] if c in df.columns), None)
        
        if first_col and last_col:
            middle_col = next((c for c in ['mname', 'middle_name'] if c in df.columns), None)
            
            if middle_col:
                df['full_name'] = df[[first_col, middle_col, last_col]].fillna('').agg(' '.join, axis=1)
            else:
                df['full_name'] = df[[first_col, last_col]].fillna('').agg(' '.join, axis=1)
            
            df['full_name'] = df['full_name'].str.replace(r'\s+', ' ', regex=True).str.strip()
            df['full_name'] = df['full_name'].replace('', 'Unknown')
        
        return df
    
    def _clean_phones(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize phone numbers to 10-digit Kenyan format"""
        phone_cols = ['phone', 'phone_number', 'mobile', 'telephone', 'tel']
        phone_col = next((c for c in phone_cols if c in df.columns), None)
        
        if phone_col:
            df[phone_col] = df[phone_col].astype(str)
            
            # Remove .0 suffix from Excel numbers
            df[phone_col] = df[phone_col].str.replace(r'\.0$', '', regex=True)
            
            # Remove non-numeric characters
            df[phone_col] = df[phone_col].str.replace(r'\D', '', regex=True)
            
            # Add leading 0 if needed
            df[phone_col] = df[phone_col].apply(
                lambda x: '0' + x if len(x) == 9 and x.startswith(('7', '1')) else x
            )
            
            # Mark invalid numbers
            df['_phone_valid'] = df[phone_col].str.match(r'^0\d{9}$').fillna(False)
            
            # Empty invalid phones
            df.loc[~df['_phone_valid'], phone_col] = ''
        
        return df
    
    def _clean_ids(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean ID/passport numbers"""
        id_cols = ['id_passport_no', 'id_number', 'national_id', 'passport', 'id_no']
        id_col = next((c for c in id_cols if c in df.columns), None)
        
        if id_col:
            df[id_col] = df[id_col].astype(str).str.strip()
            df[id_col] = df[id_col].str.replace(r'\.0$', '', regex=True)
            df[id_col] = df[id_col].replace(['nan', 'None', ''], '')
        
        return df
    
    def _clean_gender(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize gender to Male/Female"""
        gender_cols = ['sex', 'gender']
        gender_col = next((c for c in gender_cols if c in df.columns), None)
        
        if gender_col:
            df[gender_col] = df[gender_col].astype(str).str.strip().str.lower()
            
            gender_map = {
                'm': 'Male', 'male': 'Male', '1': 'Male',
                'f': 'Female', 'female': 'Female', '0': 'Female', '2': 'Female'
            }
            
            df[gender_col] = df[gender_col].map(gender_map).fillna('')
        
        return df
    
    def _process_dates_and_ages(self, df: pd.DataFrame) -> pd.DataFrame:
        """Parse dates of birth and calculate ages"""
        dob_cols = ['date_of_birth', 'dob', 'birth_date', 'birthdate']
        dob_col = next((c for c in dob_cols if c in df.columns), None)
        
        if dob_col:
            # Parse dates
            df[dob_col] = pd.to_datetime(df[dob_col], errors='coerce', dayfirst=True)
            
            # Calculate age
            today = datetime.today()
            df['age'] = df[dob_col].apply(
                lambda dob: today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                if pd.notna(dob) else None
            )
        
        return df
    
    def _basic_location_cleanup(self, df: pd.DataFrame) -> pd.DataFrame:
        """Basic location field cleanup (detailed normalization happens in enrichment)"""
        location_cols = ['county', 'constituency', 'caw', 'ward', 'polling_center', 'polling_station']
        
        for col in location_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip().str.title()
                df[col] = df[col].replace(['Nan', 'None'], '')
        
        return df
    
    # ==========================================================================
    # PHASE 2: ENRICHMENT (Asynchronous - runs after upload)
    # ==========================================================================
    
    def enrich_dataset(
        self,
        client_id: str,
        table_name: str,
        dataset_id: str,
        user_id: Optional[str] = None
    ) -> Dict:
        """
        Enrichment phase - heavy processing as background job
        
        Operations performed:
        - Advanced location name correction
        - GPS coordinate generation
        - Disability assignment
        - Training units assignment
        - File splitting by CAW
        - Summary statistics generation
        
        Args:
            client_id: The client ID
            table_name: Database table name containing the data
            dataset_id: The dataset UUID
            user_id: Optional user who triggered the job
            
        Returns:
            Dict with enrichment results
        """
        job_id = f"enrich_{client_id}_{dataset_id[:8]}_{datetime.now().strftime('%H%M%S')}"
        
        self._log(f"🚀 Starting enrichment job {job_id} for {table_name}", job_id)
        
        # Track job
        self._active_jobs[job_id] = {
            "client_id": client_id,
            "dataset_id": dataset_id,
            "table_name": table_name,
            "user_id": user_id,
            "started_at": datetime.now().isoformat(),
            "status": "running"
        }
        
        result = {
            "job_id": job_id,
            "client_id": client_id,
            "table_name": table_name,
            "status": "running",
            "records_processed": 0,
            "output_files": [],
            "errors": []
        }
        
        try:
            # Import here to avoid circular imports
            from db import engine
            
            # 1. Load data from database
            self._log("Loading data from database...", job_id)
            df = pd.read_sql(f'SELECT * FROM "{table_name}"', engine)
            result["records_processed"] = len(df)
            
            if df.empty:
                self._log("No records to enrich", job_id)
                result["status"] = "completed"
                return result
            
            # 2. Advanced location normalization
            self._log("Normalizing location names...", job_id)
            df = self._enrich_locations(df)
            
            # 3. Generate GPS coordinates
            self._log("Generating GPS coordinates...", job_id)
            df = self._enrich_gps(df)
            
            # 4. Assign disability status
            self._log("Assigning disability status...", job_id)
            df = self._enrich_disability(df)
            
            # 5. Assign training units
            self._log("Assigning training units...", job_id)
            df = self._enrich_training(df)
            
            # 6. Update database with enriched data
            self._log("Saving enriched data to database...", job_id)
            df.to_sql(table_name, engine, if_exists='replace', index=False)
            
            # 7. Create output files split by CAW
            self._log("Creating split output files...", job_id)
            output_files = self._create_split_files(df, client_id, dataset_id)
            result["output_files"] = output_files
            
            # 8. Update dataset metadata
            self._update_dataset_metadata(dataset_id, {
                "enriched": True,
                "enriched_at": datetime.utcnow().isoformat(),
                "output_files": output_files,
                "records_with_empty_phones": len(df[df.get('_phone_valid') == False]) if '_phone_valid' in df.columns else 0
            })
            
            result["status"] = "completed"
            self._active_jobs[job_id]["status"] = "completed"
            self._active_jobs[job_id]["completed_at"] = datetime.now().isoformat()
            
            self._log(f"✅ Enrichment complete. {len(output_files)} output files created.", job_id)
            
        except Exception as e:
            result["status"] = "failed"
            result["errors"].append(str(e))
            self._active_jobs[job_id]["status"] = "failed"
            self._active_jobs[job_id]["error"] = str(e)
            self._log(f"❌ Enrichment failed: {e}", job_id)
            raise
        
        return result
    
    def _enrich_locations(self, df: pd.DataFrame) -> pd.DataFrame:
        """Advanced location name normalization"""
        if 'caw' in df.columns and 'normalize_caw' in self.dfe_modules:
            df['caw_original'] = df['caw'].copy()
            df['caw'] = df['caw'].apply(self.dfe_modules['normalize_caw'])
        
        # Normalize other location fields
        for col in ['county', 'constituency', 'subcounty']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip().str.title()
        
        return df
    
    def _enrich_gps(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate GPS coordinates based on CAW"""
        if 'caw' not in df.columns:
            return df
        
        if 'get_caw_coordinates' not in self.dfe_modules:
            return df
        
        RADIUS_KM = 5
        radius_degrees = RADIUS_KM / 111
        
        def get_coords(caw):
            coords_func = self.dfe_modules.get('get_caw_coordinates')
            random_func = self.dfe_modules.get('random_coordinate')
            
            if not coords_func or not random_func:
                return {'lat': 2.206874, 'long': 40.116958}
            
            center = coords_func(caw)
            return random_func(center['lat'], center['lon'], radius_degrees)
        
        coords = df['caw'].apply(get_coords)
        df['latitude'] = coords.apply(lambda x: x['lat'])
        df['longitude'] = coords.apply(lambda x: x['long'])
        
        return df
    
    def _enrich_disability(self, df: pd.DataFrame) -> pd.DataFrame:
        """Assign disability status (2% yes, staggered distribution)"""
        num_records = len(df)
        num_yes = max(1, int(num_records * 0.02))
        
        disability_values = ['No'] * num_records
        if num_yes > 0:
            step = num_records / num_yes
            positions = [int(i * step) for i in range(num_yes)]
            for pos in positions:
                if pos < num_records:
                    disability_values[pos] = 'Yes'
        
        df['disability_status'] = disability_values
        return df
    
    def _enrich_training(self, df: pd.DataFrame) -> pd.DataFrame:
        """Assign training units completed"""
        all_units = "device_basics,internet_email,online_safety,digital_payments,egov_services,productivity"
        df['units_trained'] = all_units
        return df
    
    def _create_split_files(self, df: pd.DataFrame, client_id: str, dataset_id: str) -> List[str]:
        """Create CSV files split by CAW"""
        output_files = []
        
        if 'caw' not in df.columns or df['caw'].isna().all():
            # Save as single file if no CAW
            output_path = os.path.join(
                self.OUTPUT_DIR,
                f"{client_id}_{dataset_id[:8]}_all_records.csv"
            )
            df.to_csv(output_path, index=False)
            return [output_path]
        
        # Split by CAW
        caws = df['caw'].dropna().unique()
        
        for caw in caws:
            caw_clean = str(caw).replace(' ', '_').replace('/', '_').lower()[:20]
            caw_df = df[df['caw'] == caw].copy()
            
            output_path = os.path.join(
                self.OUTPUT_DIR,
                f"{client_id}_{dataset_id[:8]}_{caw_clean}.csv"
            )
            caw_df.to_csv(output_path, index=False)
            output_files.append(output_path)
        
        return output_files
    
    def _update_dataset_metadata(self, dataset_id: str, metadata: Dict):
        """Update the dataset record with enrichment metadata"""
        try:
            from db import SessionLocal
            from models import Dataset
            import json
            
            db = SessionLocal()
            try:
                dataset = db.query(Dataset).filter(Dataset.dataset_id == dataset_id).first()
                if dataset:
                    existing_meta = json.loads(dataset.meta) if dataset.meta else {}
                    existing_meta.update(metadata)
                    dataset.meta = json.dumps(existing_meta)
                    db.commit()
            finally:
                db.close()
                SessionLocal.remove()
        except Exception as e:
            logger.error(f"Failed to update dataset metadata: {e}")
    
    # ==========================================================================
    # INTEGRATION HELPERS
    # ==========================================================================
    
    def validate_client_access(self, user: dict, client_id: str) -> bool:
        """Validate user has access to client_id"""
        user_client_id = user.get("client_id")
        if user_client_id:
            return user_client_id == client_id
        return user.get("is_admin", False)
    
    def get_job_status(self, job_id: str) -> Optional[Dict]:
        """Get enrichment job status"""
        return self._active_jobs.get(job_id)
    
    def list_active_jobs(self, client_id: Optional[str] = None) -> List[Dict]:
        """List active enrichment jobs"""
        jobs = []
        for job_id, job_info in self._active_jobs.items():
            if client_id is None or job_info.get("client_id") == client_id:
                jobs.append({"job_id": job_id, **job_info})
        return jobs


# Create singleton instance
data_processing_service = DataProcessingService()


# ==========================================================================
# FASTAPI INTEGRATION FUNCTIONS
# ==========================================================================

def quick_clean_upload(df: pd.DataFrame) -> pd.DataFrame:
    """
    Call this from upload_service.py before saving to database
    
    Usage in upload_service.handle_upload():
        from services.dfe_automation_service import quick_clean_upload
        
        df = read_file_bytes(filename, content)
        df = quick_clean_upload(df)  # <-- Add this line
        save_dataframe_as_table(df, table_name)
    """
    return data_processing_service.quick_clean_dataframe(df)


def run_enrichment_background(
    client_id: str,
    table_name: str,
    dataset_id: str,
    user_id: Optional[str] = None
) -> str:
    """
    Queue enrichment job as background task
    
    Usage in upload endpoint:
        from services.dfe_automation_service import run_enrichment_background
        
        background_tasks.add_task(
            run_enrichment_background,
            client_id=client_id,
            table_name=table_name,
            dataset_id=dataset_id,
            user_id=current_user.get("sub")
        )
    """
    try:
        result = data_processing_service.enrich_dataset(
            client_id=client_id,
            table_name=table_name,
            dataset_id=dataset_id,
            user_id=user_id
        )
        logger.info(f"Background enrichment completed: {result['status']}")
        return result['job_id']
    except Exception as e:
        logger.error(f"Background enrichment failed: {e}")
        raise


# ==========================================================================
# OPTIONAL: Celery Task Wrapper
# ==========================================================================

def create_celery_tasks(celery_app):
    """Create Celery tasks for data processing"""
    
    @celery_app.task(bind=True, max_retries=3)
    def process_enrichment(self, client_id: str, table_name: str, dataset_id: str, user_id: str = None):
        try:
            return data_processing_service.enrich_dataset(
                client_id=client_id,
                table_name=table_name,
                dataset_id=dataset_id,
                user_id=user_id
            )
        except Exception as exc:
            self.retry(exc=exc, countdown=2 ** self.request.retries)
    
    return process_enrichment
