# Import modules

This archive separates every import from the previously supplied import list into responsibility-based files.

Example router imports:
```python
from core.fastapi_imports import APIRouter, Depends, HTTPException, Query
from database.sqlalchemy_imports import Session, and_, func
from database.session import get_db
from core.logging_config import logger
```

Use category modules as needed. Importing all categories in every router would load heavy packages (pandas, PyArrow, boto3, Celery, Pillow) unnecessarily.

The prior list's `User`, `Dataset`, `Project`, `Client`, and `DatasetMeta` imports were commented placeholders, so their actual model paths cannot be inferred. Keep importing your real models from their existing modules.

`database/session.py` is a template. If your project already configures SQLAlchemy, retain your current engine/session setup. `core/security.py` contains password/JWT utilities but intentionally does not invent `get_current_user`, which depends on your actual user model and auth flow.

Packages represented include FastAPI, Pydantic, SQLAlchemy, python-jose, passlib, httpx, requests, Celery, Redis, pandas, NumPy, PyArrow, boto3, aiofiles, Pillow, openpyxl, and pydantic-settings. Install only what your application uses. `ORJSONResponse` needs `orjson`; `EmailStr` needs `email-validator`; `pwdlib` can be installed with `pip install 'pwdlib[argon2]'`.
