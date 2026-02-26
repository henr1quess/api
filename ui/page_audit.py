"""Audit log viewer page."""

import pandas as pd
import streamlit as st

from services.audit import list_audit_dates, read_audit_log
from services.export_utils import df_to_csv_bytes, df_to_excel_bytes
from ui.components import download_section


def render():
    st.title("Auditoria – Logs de Execucao")
    st.caption("Visualize o historico de acoes realizadas no painel.")

    dates = list_audit_dates()

    if not dates:
        st.info("Nenhum log de auditoria encontrado ainda.")
        return

    selected_date = st.selectbox("Data", dates)

    entries = read_audit_log(selected_date)

    if not entries:
        st.info(f"Nenhum registro para {selected_date}.")
        return

    df = pd.DataFrame(entries)

    # Reorder columns for readability
    preferred_order = [
        "timestamp",
        "run_id",
        "action",
        "params",
        "result_counts",
        "files",
        "notes",
    ]
    cols = [c for c in preferred_order if c in df.columns] + [
        c for c in df.columns if c not in preferred_order
    ]
    df = df[cols]

    st.subheader(f"Registros: {selected_date}")
    st.dataframe(df, use_container_width=True, height=400)
    st.caption(f"{len(df)} entradas.")

    st.divider()

    download_section(
        label="Audit Log",
        df=df,
        filename_prefix=f"audit_{selected_date}",
    )
