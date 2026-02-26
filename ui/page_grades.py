"""Grades import page – full workflow with validation and simulation."""

from pathlib import Path

import pandas as pd
import streamlit as st

from activesoft_client import endpoints as ep
from services.grades import build_payloads, parse_notas_csv, validate_grades
from services.audit import generate_run_id, log_action
from services.export_utils import df_to_csv_bytes, df_to_excel_bytes, to_json_bytes
from ui.components import (
    download_section,
    loading,
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
    else:
        st.info("Template nao encontrado em templates/modelo_notas.csv")

    st.divider()

    # ── Step 1: Select context ───────────────────────────────────
    st.subheader("1. Selecionar contexto")

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

    with loading("Carregando diarios da turma..."):
        diarios_data = ep.diarios(client, turma_id)

    if not diarios_data:
        st.warning("Nenhum diario encontrado para esta turma.")
        return

    # Extract unique disciplines and fases
    disc_map = {}
    fase_map = {}
    for d in diarios_data:
        disc_id = d.get("disciplina_id") or d.get("disciplina", {}).get("id")
        disc_nome = d.get("disciplina_nome") or d.get("disciplina", {}).get("nome") or str(disc_id)
        if disc_id:
            disc_map[disc_id] = disc_nome

        fase_id = d.get("fase_nota_id") or d.get("fase_nota", {}).get("id")
        fase_nome = d.get("fase_nota_nome") or d.get("fase_nota", {}).get("nome") or str(fase_id)
        if fase_id:
            fase_map[fase_id] = fase_nome

    if not disc_map:
        st.warning("Nenhuma disciplina encontrada nos diarios.")
        return

    col1, col2 = st.columns(2)
    with col1:
        disc_label = st.selectbox(
            "Disciplina",
            [f"{v} (ID: {k})" for k, v in disc_map.items()],
        )
        disciplina_id = int(disc_label.split("ID: ")[1].rstrip(")"))
    with col2:
        if fase_map:
            fase_label = st.selectbox(
                "Fase / Nota",
                [f"{v} (ID: {k})" for k, v in fase_map.items()],
            )
            fase_nota_id = int(fase_label.split("ID: ")[1].rstrip(")"))
        else:
            fase_nota_id = st.number_input("Fase Nota ID", min_value=1, step=1)

    col_a, col_b = st.columns(2)
    with col_a:
        sobrescrever = st.checkbox("Sobrescrever nota existente", value=False)
    with col_b:
        sobrescrever_confirmada = st.checkbox(
            "Sobrescrever nota confirmada", value=False
        )

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
    st.success(
        f"Gerados **{len(payloads)} lote(s)** com **{total_notas} notas** prontas para envio."
    )

    st.warning(
        "POST esta **bloqueado** (modo simulacao). Baixe os artefatos para revisao."
    )

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
