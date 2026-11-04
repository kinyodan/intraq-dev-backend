from core.imports import *
from fastapi import APIRouter

router = APIRouter()

@router.get("/visualize/")
def visualize(
    dataset_id: str = Query(...),
    x_column: str = Query(...),
    y_column: str = Query(...),
    agg: str = Query("sum"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Perform a simple aggregation for visualization (e.g., bar chart data)."""
    try:
        ds = db.query(Dataset).filter(Dataset.dataset_id == dataset_id).first()
        if not ds:
            raise HTTPException(status_code=404, detail="Dataset not found")

        result = aggregate_for_chart(ds.table_name, x_column, y_column, agg)
        return result
    finally:
        db.close()


@router.get("/preview/")
def preview(
    dataset_id: str = Query(...), 
    limit: int = Query(100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    ):
    """Preview dataset contents (for dashboard table or quick inspection)."""
    try:
        ds = db.query(Dataset).filter(Dataset.dataset_id == dataset_id).first()
        if not ds:
            raise HTTPException(status_code=404, detail="Dataset not found")

        df = fetch_table_preview(ds.table_name, limit)
        return {"columns": df.columns.tolist(), "rows": df.to_dict(orient="records")}
    finally:
        db.close()