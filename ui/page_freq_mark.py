"""Frequency marking page – CSV upload, validate, simulate POST."""

from pathlib import Path

import streamlit as st

from services.frequency import (
    build_marcacao_payloads,
    parse_marcacao_csv,
    validate_marcacoes,
)
from services.audit import generate_run_id, log_action
from services.export_utils import to_json_bytes
from ui.components import (
    download_section,
    loading,
    require_client,
    show_validation_summary,
)

TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "templates" / "modelo_frequencia_marcacao.csv"
)


def render():
    st.title("Frequencia – Marcacao via CSV (Simulacao)")
    st.caption("POST /api/v0/marcar_frequencia_aluno/ – modo simulacao")

    _ = require_client()  # ensure connected

    # ── Template ─────────────────────────────────────────────────
    st.subheader("0. Template")
    if TEMPLATE_PATH.exists():
        st.download_button(
            "Baixar modelo_frequencia_marcacao.csv",
            data=TEMPLATE_PATH.read_bytes(),
            file_name="modelo_frequencia_marcacao.csv",
            mime="text/csv",
        )
    st.markdown(
        """
        Colunas obrigatorias: `data_hora`, `tipo_entrada_saida` (E/S), `matricula`

        Opcionais: `id_responsavel_acompanhante`, `comentario` (max 50 chars)
        """
    )

    st.divider()

    # ── Upload ───────────────────────────────────────────────────
    st.subheader("1. Upload CSV")
    uploaded = st.file_uploader(
        "CSV de marcacoes (separador ;)",
        type=["csv"],
        key="freq_mark_csv",
    )

    if uploaded is None:
        st.info("Aguardando upload do CSV.")
        return

    try:
        df = parse_marcacao_csv(uploaded.getvalue())
    except Exception as exc:
        st.error(f"Erro ao ler CSV: {exc}")
        return

    # ── Preview ──────────────────────────────────────────────────
    st.subheader("2. Preview")
    st.dataframe(df, use_container_width=True)
    st.caption(f"{len(df)} linhas carregadas.")

    st.divider()

    # ── Validate ─────────────────────────────────────────────────
    st.subheader("3. Validacao")
    if st.button("Validar", key="btn_validate_freq_mark"):
        with loading("Validando..."):
            validated = validate_marcacoes(df)
        st.session_state["freq_mark_validated"] = validated

    validated = st.session_state.get("freq_mark_validated")
    if validated is None:
        st.info("Clique em 'Validar' para continuar.")
        return

    show_validation_summary(validated)

    st.divider()

    # ── Build payloads ───────────────────────────────────────────
    st.subheader("4. Gerar Payloads (simulacao)")

    if st.button("Gerar payloads", key="btn_gen_freq_mark"):
        run_id = generate_run_id()
        payloads = build_marcacao_payloads(validated)

        st.session_state["freq_mark_payloads"] = payloads
        st.session_state["freq_mark_run_id"] = run_id

        log_action(
            run_id=run_id,
            action="frequency_mark_simulation",
            params={},
            result_counts={
                "total_linhas": len(validated),
                "ok": int((validated["_status"] == "OK").sum()),
                "erro": int((validated["_status"] == "ERRO").sum()),
                "payloads": len(payloads),
            },
        )

    payloads = st.session_state.get("freq_mark_payloads")
    if payloads is None:
        return

    # ── Results ──────────────────────────────────────────────────
    st.subheader("5. Resultado da simulacao")

    run_id = st.session_state.get("freq_mark_run_id", "")
    st.caption(f"Run ID: `{run_id}`")
    st.success(f"Gerados **{len(payloads)} payload(s)** de marcacao.")
    st.warning("POST **bloqueado** (modo simulacao). Baixe os artefatos para revisao.")

    download_section(
        label="Relatorio de validacao",
        df=validated,
        filename_prefix=f"freq_marcacao_validacao_{run_id}",
    )

    st.download_button(
        "JSON – Payloads completos",
        data=to_json_bytes(payloads),
        file_name=f"freq_marcacao_payloads_{run_id}.json",
        mime="application/json",
    )
