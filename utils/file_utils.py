# utils/file_utils.py
import pandas as pd
import io

def read_file_bytes(filename: str, content: bytes) -> pd.DataFrame:
    lower = filename.lower()
    if lower.endswith(".csv"):
        return pd.read_csv(io.BytesIO(content))
    if lower.endswith(".tsv"):
        return pd.read_csv(io.BytesIO(content), sep="\t")
    if lower.endswith((".xls", ".xlsx")):
        return pd.read_excel(io.BytesIO(content))
    if lower.endswith(".json"):
        return pd.read_json(io.BytesIO(content))
    # fallback try CSV
    return pd.read_csv(io.BytesIO(content))
