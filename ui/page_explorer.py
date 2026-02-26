"""Data Explorer page – query any GET endpoint and export results."""

import pandas as pd
import streamlit as st

from activesoft_client import endpoints as ep
from activesoft_client.endpoints import EXPLORER_ENDPOINTS
from services.audit import generate_run_id, log_action
from services.export_utils import records_to_df
from ui.components import download_section, loading, require_client


def render():
    st.title("Explorer de Dados")
    st.caption("Consulte qualquer endpoint GET disponivel e exporte os resultados.")

    client = require_client()

    # ── Select endpoint ──────────────────────────────────────────
    endpoint_keys = list(EXPLORER_ENDPOINTS.keys())
    descriptions = [EXPLORER_ENDPOINTS[k]["description"] for k in endpoint_keys]
    display_options = [f"{d} ({k})" for k, d in zip(endpoint_keys, descriptions)]

    selected_display = st.selectbox("Endpoint", display_options)
    selected_key = endpoint_keys[display_options.index(selected_display)]
    endpoint_info = EXPLORER_ENDPOINTS[selected_key]

    # ── Query params ─────────────────────────────────────────────
    params = {}
    if endpoint_info["params"]:
        st.subheader("Parametros")
        for param_name in endpoint_info["params"]:
            val = st.text_input(
                param_name,
                value="",
                key=f"explorer_param_{param_name}",
                help=f"Parametro '{param_name}' (deixe vazio para ignorar)",
            )
            if val.strip():
                params[param_name] = val.strip()

    st.divider()

    # ── Execute ──────────────────────────────────────────────────
    if st.button("Consultar", key="btn_explorer_query"):
        run_id = generate_run_id()

        with loading(f"Buscando {selected_key}..."):
            try:
                data = client.get_all(endpoint_info["path"], params=params or None)
            except Exception as exc:
                st.error(f"Erro na requisicao: {exc}")
                return

        df = records_to_df(data) if isinstance(data, list) else pd.DataFrame()

        st.session_state["explorer_data"] = data
        st.session_state["explorer_df"] = df
        st.session_state["explorer_run_id"] = run_id
        st.session_state["explorer_endpoint"] = selected_key

        log_action(
            run_id=run_id,
            action=f"explorer_{selected_key}",
            params=params,
            result_counts={"registros": len(df)},
        )

    df = st.session_state.get("explorer_df")
    data = st.session_state.get("explorer_data")
    run_id = st.session_state.get("explorer_run_id", "")
    ep_name = st.session_state.get("explorer_endpoint", "")

    if df is None:
        st.info("Selecione um endpoint e clique 'Consultar'.")
        return

    # ── Display results ──────────────────────────────────────────
    st.subheader(f"Resultado: {ep_name}")
    st.caption(f"{len(df)} registros. Run ID: `{run_id}`")

    if df.empty:
        st.warning("Nenhum registro retornado.")
        return

    st.dataframe(df, use_container_width=True, height=400)

    st.divider()

    # ── Downloads ────────────────────────────────────────────────
    st.subheader("Exportar")
    download_section(
        label=ep_name,
        df=df,
        json_data=data,
        filename_prefix=f"explorer_{ep_name}_{run_id}",
    )
