"""Grades import page – full workflow with validation and simulation."""

from pathlib import Path

import pandas as pd
import streamlit as st

from activesoft_client import endpoints as ep
from services.grades import build_payloads, parse_notas_csv, validate_grades
from services.audit import generate_run_id, log_action
from services.export_utils import to_json_bytes
from ui.components import (
    cached_fetch,
    download_section,
    format_turma_label,
    loading,
    parse_diarios,
    require_client,
    show_validation_summary,
)

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "modelo_notas.csv"


def render():
    st.title("Importar Notas em Lote (Simulacao)")
    st.caption("Baseado no endpoint POST /api/v0/correcao_prova/")

    client = require_client()

    # ── Step 0: Download template ────────────────────────────────
    st.subheader("0. Template")
    if TEMPLATE_PATH.exists():
        st.download_button(
            "Baixar modelo_notas.csv",
            data=TEMPLATE_PATH.read_bytes(),
            file_name="modelo_notas.csv",
            mime="text/csv",
        )

    st.divider()

    # ── Step 1: Select context (cached) ──────────────────────────
    st.subheader("1. Selecionar contexto")

    df_turmas, _ = cached_fetch(
        endpoint_name="lista_turmas",
        endpoint_path="/api/v0/lista_turmas/",
        fetch_fn=lambda: ep.lista_turmas(client),
        params={"mostrar_todas_as_turmas": "true"},
        st_key="grades_turmas",
    )

    if df_turmas is None or df_turmas.empty:
        st.warning("Nenhuma turma encontrada.")
        return

    turmas = df_turmas.to_dict("records")
    turma_options = {format_turma_label(t): t for t in turmas}
    turma_label = st.selectbox("Turma", list(turma_options.keys()), key="grades_turma_sel")
    turma = turma_options[turma_label]
    turma_id = turma.get("id")

    # Diarios (cached per turma)
    df_diarios, _ = cached_fetch(
        endpoint_name="diarios",
        endpoint_path="/api/v0/diarios/",
        fetch_fn=lambda tid=turma_id: ep.diarios(client, tid),
        params={"turma": str(turma_id)},
        st_key=f"grades_diarios_{turma_id}",
    )

    if df_diarios is None or df_diarios.empty:
        st.warning("Nenhum diario encontrado para esta turma.")
        return

    diarios_data = df_diarios.to_dict("records")
    disc_map, fase_map = parse_diarios(diarios_data)

    if not disc_map:
        st.warning("Nenhuma disciplina encontrada nos diarios.")
        return

    col1, col2 = st.columns(2)
    with col1:
        disc_options = [f"{v} (ID: {k})" for k, v in disc_map.items()]
        disc_label = st.selectbox("Disciplina", disc_options)
        disciplina_id = int(disc_label.split("ID: ")[1].rstrip(")"))
    with col2:
        if fase_map:
            fase_options = [f"{v} (ID: {k})" for k, v in fase_map.items()]
            fase_label = st.selectbox("Fase / Nota", fase_options)
            fase_nota_id = int(fase_label.split("ID: ")[1].rstrip(")"))
        else:
            fase_nota_id = st.number_input("Fase Nota ID", min_value=1, step=1)

    col_a, col_b = st.columns(2)
    with col_a:
        sobrescrever = st.checkbox("Sobrescrever nota existente", value=False)
    with col_b:
        sobrescrever_confirmada = st.checkbox("Sobrescrever nota confirmada", value=False)

    st.divider()

    # ── Step 2: Upload CSV ───────────────────────────────────────
    st.subheader("2. Upload CSV")
    uploaded = st.file_uploader(
        "Selecione o CSV de notas (separador ;)",
        type=["csv"],
        key="grades_csv",
    )

    if uploaded is None:
        st.info("Aguardando upload do arquivo CSV.")
        return

    try:
        df = parse_notas_csv(uploaded.getvalue())
    except Exception as exc:
        st.error(f"Erro ao ler CSV: {exc}")
        return

    # ── Step 3: Preview ──────────────────────────────────────────
    st.subheader("3. Preview dos dados")
    st.dataframe(df, use_container_width=True)
    st.caption(f"{len(df)} linhas carregadas.")
    st.divider()

    # ── Step 4: Validate ─────────────────────────────────────────
    st.subheader("4. Validacao")
    if st.button("Validar dados", key="btn_validate_grades"):
        with loading("Validando..."):
            validated = validate_grades(df, client, turma_id, disciplina_id, fase_nota_id)
        st.session_state["grades_validated"] = validated

    validated = st.session_state.get("grades_validated")
    if validated is None:
        st.info("Clique em 'Validar dados' para continuar.")
        return

    show_validation_summary(validated)
    st.divider()

    # ── Step 5: Generate payloads ────────────────────────────────
    st.subheader("5. Gerar Payloads (simulacao)")
    batch_size = st.number_input("Tamanho do lote", min_value=1, value=200, step=50)

    if st.button("Gerar payloads", key="btn_gen_payloads"):
        run_id = generate_run_id()
        payloads = build_payloads(
            validated,
            turma_id=turma_id,
            disciplina_id=disciplina_id,
            fase_nota_id=fase_nota_id,
            sobrescrever_nota=sobrescrever,
            sobrescrever_nota_confirmada=sobrescrever_confirmada,
            batch_size=batch_size,
        )
        st.session_state["grades_payloads"] = payloads
        st.session_state["grades_run_id"] = run_id

        ok_count = int((validated["_status"] == "OK").sum())
        log_action(
            run_id=run_id,
            action="grades_import_simulation",
            params={
                "turma_id": turma_id,
                "disciplina_id": disciplina_id,
                "fase_nota_id": fase_nota_id,
                "sobrescrever_nota": sobrescrever,
                "batch_size": batch_size,
            },
            result_counts={
                "total_linhas": len(validated),
                "ok": ok_count,
                "erro": int((validated["_status"] == "ERRO").sum()),
                "warn": int((validated["_status"] == "WARN").sum()),
                "batches": len(payloads),
            },
        )

    payloads = st.session_state.get("grades_payloads")
    if payloads is None:
        return

    # ── Step 6: Results & downloads ──────────────────────────────
    st.subheader("6. Resultado da simulacao")

    run_id = st.session_state.get("grades_run_id", "")
    st.caption(f"Run ID: `{run_id}`")

    total_notas = sum(len(p.get("notas", [])) for p in payloads)
    st.success(f"Gerados **{len(payloads)} lote(s)** com **{total_notas} notas** prontas para envio.")
    st.warning("POST esta **bloqueado** (modo simulacao). Baixe os artefatos para revisao.")

    download_section(
        label="Relatorio de validacao",
        df=validated,
        filename_prefix=f"notas_validacao_{run_id}",
        excel_sheets={
            "Validacao": validated,
            "Somente OK": validated[validated["_status"] == "OK"],
        },
    )

    st.download_button(
        "JSON – Payloads completos",
        data=to_json_bytes(payloads),
        file_name=f"notas_payloads_{run_id}.json",
        mime="application/json",
    )
