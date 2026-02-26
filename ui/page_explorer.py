"""Data Explorer page – query any GET endpoint and export results."""

import pandas as pd
import streamlit as st

from activesoft_client.endpoints import EXPLORER_ENDPOINTS
from services.audit import generate_run_id, log_action
from ui.components import (
    cached_fetch,
    download_section,
    require_client,
)


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

    # ── Fetch (cached) ───────────────────────────────────────────
    # Build a unique st_key using endpoint + params
    params_suffix = "_".join(f"{k}{v}" for k, v in sorted(params.items())) if params else "noparams"
    st_key = f"explorer_{selected_key}_{params_suffix}"

    df, meta = cached_fetch(
        endpoint_name=selected_key,
        endpoint_path=endpoint_info["path"],
        fetch_fn=lambda: client.get_all(endpoint_info["path"], params=params or None),
        params=params or None,
        st_key=st_key,
    )

    if df is None or df.empty:
        st.info("Nenhum registro retornado.")
        return

    run_id = generate_run_id()

    log_action(
        run_id=run_id,
        action=f"explorer_{selected_key}",
        params=params,
        result_counts={"registros": len(df)},
    )

    # ── Display results ──────────────────────────────────────────
    st.subheader(f"Resultado: {selected_key}")
    st.caption(f"{len(df)} registros. Run ID: `{run_id}`")
    st.dataframe(df, use_container_width=True, height=400)

    st.divider()

    # ── Downloads ────────────────────────────────────────────────
    st.subheader("Exportar")

    # Use sanitized name for filenames (no slash)
    safe_name = selected_key.replace("/", "_")
    download_section(
        label=safe_name,
        df=df,
        json_data=df.to_dict("records"),
        filename_prefix=f"explorer_{safe_name}_{run_id}",
    )
