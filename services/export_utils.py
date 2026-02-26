"""Export helpers: CSV, Excel, JSON for Streamlit downloads."""

import io
import json
from typing import Any, Dict, List, Optional

import pandas as pd


def df_to_csv_bytes(df: pd.DataFrame, sep: str = ";") -> bytes:
    """DataFrame -> CSV bytes (UTF-8 BOM, semicolon separator)."""
    return df.to_csv(index=False, sep=sep, encoding="utf-8-sig").encode("utf-8-sig")


def df_to_excel_bytes(
    sheets: Dict[str, pd.DataFrame],
) -> bytes:
    """Dict of {sheet_name: DataFrame} -> Excel (.xlsx) bytes."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
    return buf.getvalue()


def to_json_bytes(data: Any, ensure_ascii: bool = False) -> bytes:
    """Serialize data to pretty JSON bytes."""
    return json.dumps(data, indent=2, ensure_ascii=ensure_ascii, default=str).encode(
        "utf-8"
    )


def records_to_df(records: List[Dict]) -> pd.DataFrame:
    """List of dicts -> DataFrame, handling empty lists."""
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)
