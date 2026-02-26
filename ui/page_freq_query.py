"""Frequency query page – consult attendance data and export."""

import streamlit as st

from activesoft_client import endpoints as ep
from services.frequency import fetch_frequencia_raw, summarize_frequencia
from services.audit import generate_run_id, log_action
from services.export_utils import df_to_csv_bytes, df_to_excel_bytes
from ui.components import download_section, loading, require_client


def render():
    st.title("Frequencia – Consulta por Diario")
    st.caption("GET /api/v0/diario_frequencia/")

    client = require_client()

    # ── Select turma ─────────────────────────────────────────────
    with loading("Carregando turmas..."):
        turmas = ep.lista_turmas(client)

    if not turmas:
        st.warning("Nenhuma turma encontrada.")
        return

    turma_options = {}
    for t in turmas:
        nome = t.get("nome_turma_completo") or t.get("nome_turma") or f"ID {t.get('id')}"
        turma_options[nome] = t
    turma_label = st.selectbox("Turma", list(turma_options.keys()))
    turma = turma_options[turma_label]
    turma_id = turma.get("id")

    # ── Select diario ────────────────────────────────────────────
    with loading("Carregando diarios..."):
        diarios_data = ep.diarios(client, turma_id)

    if not diarios_data:
        st.warning("Nenhum diario encontrado para esta turma.")
        return

    diario_options = {}
    for d in diarios_data:
        did = d.get("id")
        disc = d.get("disciplina_nome") or d.get("disciplina", {}).get("nome", "")
        fase = d.get("fase_nota_nome") or d.get("fase_nota", {}).get("nome", "")
        label = f"{disc} / {fase} (ID: {did})"
        diario_options[label] = did

    diario_label = st.selectbox("Diario", list(diario_options.keys()))
    diario_id = diario_options[diario_label]

    st.divider()

    # ── Fetch frequency ──────────────────────────────────────────
    if st.button("Consultar frequencia", key="btn_fetch_freq"):
        run_id = generate_run_id()

        with loading("Buscando dados de frequencia..."):
            df_raw = fetch_frequencia_raw(client, diario_id)

        if df_raw.empty:
            st.warning("Nenhum dado de frequencia retornado.")
            return

        df_summary = summarize_frequencia(df_raw)

        st.session_state["freq_raw"] = df_raw
        st.session_state["freq_summary"] = df_summary
        st.session_state["freq_run_id"] = run_id

        log_action(
            run_id=run_id,
            action="frequency_query",
            params={"turma_id": turma_id, "diario_id": diario_id},
            result_counts={
                "registros_bruto": len(df_raw),
                "registros_resumo": len(df_summary),
            },
        )

    df_raw = st.session_state.get("freq_raw")
    df_summary = st.session_state.get("freq_summary")
    run_id = st.session_state.get("freq_run_id", "")

    if df_raw is None:
        st.info("Clique em 'Consultar frequencia' para buscar os dados.")
        return

    # ── Display results ──────────────────────────────────────────
    st.subheader("Dados brutos")
    st.dataframe(df_raw, use_container_width=True, height=300)
    st.caption(f"{len(df_raw)} registros. Run ID: `{run_id}`")

    if df_summary is not None and not df_summary.empty:
        st.subheader("Resumo por aluno")
        st.dataframe(df_summary, use_container_width=True, height=300)

    st.divider()

    # ── Downloads ────────────────────────────────────────────────
    st.subheader("Exportar")

    sheets = {"Bruto": df_raw}
    if df_summary is not None and not df_summary.empty:
        sheets["Resumo"] = df_summary

    download_section(
        label="Frequencia bruto",
        df=df_raw,
        filename_prefix=f"frequencia_bruto_{run_id}",
    )

    if df_summary is not None and not df_summary.empty:
        download_section(
            label="Frequencia resumo",
            df=df_summary,
            filename_prefix=f"frequencia_resumo_{run_id}",
        )

    # Combined Excel with both sheets
    st.download_button(
        "Excel – Bruto + Resumo",
        data=df_to_excel_bytes(sheets),
        file_name=f"frequencia_completo_{run_id}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
