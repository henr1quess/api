"""Shared Streamlit UI components."""

from typing import Dict, Optional

import pandas as pd
import streamlit as st

from services.export_utils import df_to_csv_bytes, df_to_excel_bytes, to_json_bytes


def require_client():
    """Return the API client from session state, or show error and stop."""
    client = st.session_state.get("client")
    if client is None:
        st.warning("Configure o token da API na barra lateral para continuar.")
        st.stop()
    return client


def download_section(
    label: str,
    df: Optional[pd.DataFrame] = None,
    json_data=None,
    filename_prefix: str = "export",
    excel_sheets: Optional[Dict[str, pd.DataFrame]] = None,
):
    """Render download buttons for CSV, Excel, and/or JSON."""
    cols = st.columns(3)

    if df is not None and not df.empty:
        with cols[0]:
            st.download_button(
                f"CSV – {label}",
                data=df_to_csv_bytes(df),
                file_name=f"{filename_prefix}.csv",
                mime="text/csv",
            )
        with cols[1]:
            sheets = excel_sheets or {label[:31]: df}
            st.download_button(
                f"Excel – {label}",
                data=df_to_excel_bytes(sheets),
                file_name=f"{filename_prefix}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    if json_data is not None:
        with cols[2]:
            st.download_button(
                f"JSON – {label}",
                data=to_json_bytes(json_data),
                file_name=f"{filename_prefix}.json",
                mime="application/json",
            )


def show_validation_summary(df: pd.DataFrame):
    """Show a colored summary of validation results."""
    if "_status" not in df.columns:
        return

    ok = int((df["_status"] == "OK").sum())
    warn = int((df["_status"] == "WARN").sum())
    erro = int((df["_status"] == "ERRO").sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("OK", ok)
    c2.metric("WARN", warn)
    c3.metric("ERRO", erro)

    if erro > 0:
        with st.expander(f"Ver {erro} erros", expanded=True):
            st.dataframe(
                df[df["_status"] == "ERRO"][["matricula", "_status", "_msg"]],
                use_container_width=True,
            )
    if warn > 0:
        with st.expander(f"Ver {warn} avisos"):
            st.dataframe(
                df[df["_status"] == "WARN"][["matricula", "_status", "_msg"]],
                use_container_width=True,
            )


def loading(msg: str = "Carregando dados..."):
    """Context manager wrapper for st.spinner."""
    return st.spinner(msg)
