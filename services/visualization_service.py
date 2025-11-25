# services/visualization_service.py
import pandas as pd
from db import engine
import json

def fetch_table_preview(table_name: str, limit: int = 100):
    query = f"SELECT * FROM {table_name} LIMIT {limit}"
    df = pd.read_sql(query, engine)
    return df

def aggregate_for_chart(table_name: str, x_column: str, y_column: str, agg: str = "sum", group_limit: int = 1000):
    """
    Simple aggregator: group by x_column and aggregate on y_column
    returns {"x": [...], "y": [...] }
    """
    # sanitize identifiers in production!
    q = f"SELECT \"{x_column}\" as x, {agg}(\"{y_column}\") as y FROM {table_name} GROUP BY \"{x_column}\" ORDER BY x LIMIT {group_limit}"
    try:
        df = pd.read_sql(q, engine)
    except Exception:
        # fallback: fetch table and compute in pandas
        df_full = pd.read_sql(f"SELECT \"{x_column}\", \"{y_column}\" FROM {table_name}", engine)
        df = df_full.groupby(x_column).agg({y_column: agg}).reset_index().rename(columns={x_column: "x", y_column: "y"})
    # Coerce types for JSON
    x = df["x"].astype(str).tolist()
    y = pd.to_numeric(df["y"], errors="coerce").fillna(0).tolist()
    return {"x": x, "y": y, "series_name": y_column}
