"""Frequency query page – consult attendance data and export."""

import streamlit as st

from activesoft_client import endpoints as ep
from services.frequency import summarize_frequencia
from services.audit import generate_run_id, log_action
from services.export_utils import df_to_excel_bytes
from ui.components import (
    cached_fetch,
    download_section,
    format_diario_label,
    format_turma_label,
    require_client,
)


def render():
    st.title("Frequencia – Consulta por Diario")
    st.caption("GET /api/v0/diario_frequencia/")

    client = require_client()

    # ── Select turma (cached) ────────────────────────────────────
    df_turmas, _ = cached_fetch(
        endpoint_name="lista_turmas",
        endpoint_path="/api/v0/lista_turmas/",
        fetch_fn=lambda: ep.lista_turmas(client),
        params={"mostrar_todas_as_turmas": "true"},
        st_key="freq_q_turmas",
    )

    if df_turmas is None or df_turmas.empty:
        st.warning("Nenhuma turma encontrada.")
        return

    turmas = df_turmas.to_dict("records")
    turma_options = {format_turma_label(t): t for t in turmas}
    turma_label = st.selectbox("Turma", list(turma_options.keys()), key="freq_q_turma_sel")
    turma = turma_options[turma_label]
    turma_id = turma.get("id")

    # ── Select diario (cached per turma) ─────────────────────────
    df_diarios, _ = cached_fetch(
        endpoint_name="diarios",
        endpoint_path="/api/v0/diarios/",
        fetch_fn=lambda tid=turma_id: ep.diarios(client, tid),
        params={"turma": str(turma_id)},
        st_key=f"freq_q_diarios_{turma_id}",
    )

    if df_diarios is None or df_diarios.empty:
        st.warning("Nenhum diario encontrado para esta turma.")
        return

    diarios_data = df_diarios.to_dict("records")
    diario_options = {format_diario_label(d): d.get("id") for d in diarios_data if isinstance(d, dict)}

    if not diario_options:
        st.warning("Nenhum diario valido encontrado.")
        return

    diario_label = st.selectbox("Diario", list(diario_options.keys()), key="freq_q_diario_sel")
    diario_id = diario_options[diario_label]

    st.divider()

    # ── Fetch frequency (cached per diario) ──────────────────────
    df_raw, meta = cached_fetch(
        endpoint_name="diario_frequencia",
        endpoint_path="/api/v0/diario_frequencia/",
        fetch_fn=lambda did=diario_id: ep.diario_frequencia(client, did),
        params={"diario": str(diario_id)},
        st_key=f"freq_q_freq_{diario_id}",
    )

    if df_raw is None or df_raw.empty:
        st.warning("Nenhum dado de frequencia retornado.")
        return

    run_id = generate_run_id()

    # Summarize
    df_summary = summarize_frequencia(df_raw)

    log_action(
        run_id=run_id,
        action="frequency_query",
        params={"turma_id": turma_id, "diario_id": diario_id},
        result_counts={
            "registros_bruto": len(df_raw),
            "registros_resumo": len(df_summary),
        },
    )

    # ── Enrich with student names if not already present ─────────
    _name_cols = ["nome_aluno", "nome", "nome_completo", "aluno"]
    if not any(c in df_raw.columns for c in _name_cols):
        try:
            id_col = next(
                (c for c in ["aluno_id", "matricula", "id_aluno"] if c in df_raw.columns),
                None,
            )
            if id_col:
                alunos_raw = ep.acesso_alunos(client)
                nome_map = {
                    str(a.get("id_aluno") or a.get("id")): (
                        a.get("nome_aluno") or a.get("nome") or ""
                    )
                    for a in alunos_raw
                    if a.get("id_aluno") or a.get("id")
                }
                if nome_map:
                    df_raw = df_raw.copy()
                    df_raw.insert(
                        0, "nome_aluno",
                        df_raw[id_col].astype(str).map(nome_map).fillna(""),
                    )
                    if not df_summary.empty:
                        df_summary = df_summary.copy()
                        df_summary.insert(
                            0, "nome_aluno",
                            df_summary[id_col].astype(str).map(nome_map).fillna(""),
                        )
        except Exception:
            pass  # best-effort; don't block the page

    # ── Display results ──────────────────────────────────────────
    st.subheader("Dados brutos")
    st.dataframe(df_raw, use_container_width=True, height=300)
    st.caption(f"{len(df_raw)} registros. Run ID: `{run_id}`")

    if not df_summary.empty:
        st.subheader("Resumo por aluno")
        st.dataframe(df_summary, use_container_width=True, height=300)

    st.divider()

    # ── Downloads ────────────────────────────────────────────────
    st.subheader("Exportar")

    sheets = {"Bruto": df_raw}
    if not df_summary.empty:
        sheets["Resumo"] = df_summary

    download_section(
        label="Frequencia bruto",
        df=df_raw,
        filename_prefix=f"frequencia_bruto_{run_id}",
    )

    if not df_summary.empty:
        download_section(
            label="Frequencia resumo",
            df=df_summary,
            filename_prefix=f"frequencia_resumo_{run_id}",
        )

    st.download_button(
        "Excel – Bruto + Resumo",
        data=df_to_excel_bytes(sheets),
        file_name=f"frequencia_completo_{run_id}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
