# Intraq - Flexible Dataset Ingest & Visualization API

## What this provides
- upload endpoint that accepts CSV/TSV/Excel/JSON
- automatic schema inference and metadata storage
- data stored as tables (one per dataset) in the configured DB
- basic visualization/aggregation endpoints returning chart-ready JSON
- preview endpoint to see sample rows

## Quick start (dev)
1. create and activate a venv


2. copy `.env.example` -> `.env` and adjust `DATABASE_URL` if needed.

3. run


4. API endpoints:
- `POST /upload_dataset/` multipart form:
  - `client_id` (form field)
  - `file` (file)
  returns `dataset_id` and schema.
- `GET /datasets/?client_id=...` lists datasets
- `GET /datasets/{dataset_id}/schema` returns schema
- `GET /visualize/?dataset_id=...&x_column=...&y_column=...&agg=sum` returns `{x:[], y:[], series_name: ...}`
- `GET /preview/?dataset_id=...&limit=100`

## Notes & production considerations
- **DB choice**: For dev we used SQLite but use Postgres for production. If datasets become large, write dataset tables to a dedicated analytics DB (e.g., Postgres schema or DuckDB / Parquet store).
- **Sanitize table/column names** before using raw SQL to avoid injection.
- **Auth**: add client authentication (API keys or OAuth) to ensure multi-tenant isolation.
- **Background processing**: large file parsing should be moved to background worker (Celery / RQ) and report progress to user.
- **Storage**: store raw files in S3/MinIO for auditing and reprocessing.
- **Indexing**: add indexes for columns used frequently (date fields, categories).
- **Schema mapping**: add a mapping UI for clients to indicate which column is "date", "amount", etc.
- **Profiling**: optionally run `ydata-profiling` reports or pivot suggestions after upload to help clients pick useful visualizations.
