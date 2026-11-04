# ============================================================
# STANDARD PYTHON IMPORTS
# ============================================================

from core.core.standard_imports import *

# ============================================================
# FASTAPI IMPORTS
# ============================================================

from core.core.fastapi_imports import *

# ============================================================
# PYDANTIC IMPORTS
# ============================================================

from core.core.pydantic_imports import *

# ============================================================
# SECURITY IMPORTS
# ============================================================

from core.core.security_imports import *

# ============================================================
# LOGGING
# ============================================================

from core.core.logging_config import *

# ============================================================
# DATABASE IMPORTS AND MIGRATIONS IMPORTS
# ============================================================
from alembic import command
from alembic.config import Config

from core.database.sqlalchemy_imports import *
from core.database.async_sqlalchemy_imports import *

# ============================================================
# DATABASE SESSION
# ============================================================

from core.database.session import get_db

# ============================================================
# HTTP CLIENT IMPORTS
# ============================================================

from core.services.http_imports import *

# ============================================================
# DATA PROCESSING IMPORTS
# ============================================================

from core.services.data_imports import *

# ============================================================
# STORAGE IMPORTS
# ============================================================

from core.services.storage_imports import *

# ============================================================
# FILE HANDLING IMPORTS
# ============================================================

from core.services.file_imports import *

# ============================================================
# QUEUE IMPORTS
# ============================================================

from core.tasks.queue_imports import *


# ============================================================
# DATABASE AND REDIS
# ============================================================

from db import SessionLocal, engine, DATABASE_URL
from redis_db import init_redis_db


# ============================================================
# APPLICATION MODELS
# ============================================================

from models import (
    Base,
    UserSession,
    AuthCode,
    User,
    Dataset,
    DatasetMeta,
    Package,
)

# ============================================================
# APPLICATION SCHEMAS
# ============================================================

from schemas import (
    DatasetCreateResponse,
    DatasetInfo,
)

# ============================================================
# ONBOARDING AND UPLOAD SERVICES
# ============================================================

from services.onboarding_service import process_onboarding
from services.upload_service import handle_upload


# ============================================================
# VISUALIZATION SERVICES
# ============================================================

from services.visualization_service import (
    aggregate_for_chart,
    fetch_table_preview,
)


# ============================================================
# REDIS EMAIL SERVICES
# ============================================================

from services.redis_service import (
    save_email_to_redis,
    get_emails_sync,
    get_emails_by_ids,
    get_email,
    save_reply_email_to_redis,
)


# ============================================================
# EMAIL SERVICES AND IMPORTS
# ============================================================
import resend

from services.resend_service import get_full_email

from services.email_service import (
    EmailInboxService,
    IntraqTemplates,
)


# ============================================================
# TELEGRAM SERVICES
# ============================================================

from services.telegram_service import send_telegram_msg


# ============================================================
# DATASET AND PROJECT DELETION SERVICES
# ============================================================

from services.delete_service import (
    soft_delete_dataset,
    restore_dataset,
    list_trashed_datasets,
    permanently_delete_dataset,
    soft_delete_project,
    restore_project,
    list_trashed_projects,
    permanently_delete_project,
)


# ============================================================
# CLOUDFLARE R2 SERVICES
# ============================================================

from services.cloudflare_service import (
    create_user_r2_structure,
    create_project_r2_structure,
    get_directory_tree,
)
