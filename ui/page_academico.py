"""Academic dashboard page — 4 tabs.

Tabs: Frequencia Consulta | Farol de Risco | Auditoria de Diarios | Consulta Boletim
"""

import streamlit as st
import pandas as pd

from ui.components import require_client, get_cache_store, download_section
from ui import page_freq_query
from services.export_utils import df_to_excel_bytes
from activesoft_client.endpoints import acesso_alunos, lista_turmas


def render():
    st.title("🎓 Academico")

    tab_freq, tab_risco, tab_audit, tab_boletim = st.tabs([
        "📋 Frequencia – Consulta",
        "🚦 Farol de Risco",
        "📝 Auditoria de Diarios",
        "📖 Consulta Boletim",
    ])

    with tab_freq:
        page_freq_query.render()

    with tab_risco:
        _render_farol_risco()

    with tab_audit:
        _render_auditoria_diarios()

    with tab_boletim:
        _render_consulta_boletim()


# ═══════════════════════════════════════════════════════════════════
# Tab: Farol de Risco
# ═══════════════════════════════════════════════════════════════════

def _render_farol_risco():
    """Student risk detection dashboard."""
    from services.pedagogico import (
        fetch_all_frequencia_aluno,
        fetch_all_boletins,
        detect_risco_evasao,
    )

    st.subheader("Farol de Risco — Evasao e Reprovacao")
    st.caption(
        "Identifica alunos com sinais de risco: faltas excessivas, "
        "notas criticas, ou ambos. Permite acao preventiva da coordenacao."
    )

    client = require_client()
    store = get_cache_store()

    # ── Load controls ────────────────────────────────────────────
    col_load, col_info = st.columns([1, 3])
    with col_load:
        if st.button(
            "📥 Carregar / Atualizar dados pedagogicos",
            key="btn_load_pedagogico",
            use_container_width=True,
        ):
            st.session_state["_ped_force_refresh"] = True

    force = st.session_state.pop("_ped_force_refresh", False)
    freq_df = st.session_state.get("ped_freq_df", pd.DataFrame())
    boletim_df = st.session_state.get("ped_boletim_df", pd.DataFrame())

    if force or (freq_df.empty and boletim_df.empty):
        if force:
            try:
                alunos_ativos = acesso_alunos(client)
                alunos_ids = [a.get("id_aluno", a.get("id", a.get("aluno_id")))
                              for a in alunos_ativos if a.get("id_aluno") or a.get("id")]
                alunos_ids = [int(x) for x in alunos_ids if x is not None]

                if not alunos_ids:
                    st.warning("Nenhum aluno ativo encontrado.")
                    return

                # Fetch frequency
                freq_df, freq_meta = fetch_all_frequencia_aluno(
                    client, store, alunos_ids,
                    data_inicial="2026-01-01",
                    force_refresh=force,
                )
                st.session_state["ped_freq_df"] = freq_df
                st.session_state["ped_freq_meta"] = freq_meta

                # Fetch report cards
                boletim_df, bol_meta = fetch_all_boletins(
                    client, store, alunos_ids,
                    force_refresh=force,
                )
                st.session_state["ped_boletim_df"] = boletim_df
                st.session_state["ped_boletim_meta"] = bol_meta

            except Exception as e:
                st.error(f"Erro ao carregar dados pedagogicos: {e}")
                return

    if freq_df.empty and boletim_df.empty:
        with col_info:
            st.info("Clique em **Carregar dados pedagogicos** para baixar os dados da API.")
        return

    # Show data info
    freq_meta = st.session_state.get("ped_freq_meta")
    bol_meta = st.session_state.get("ped_boletim_meta")
    with col_info:
        info_parts = []
        if freq_meta:
            info_parts.append(f"Frequencia: {freq_meta.rows} registros ({freq_meta.age_str()})")
        if bol_meta:
            info_parts.append(f"Boletins: {bol_meta.rows} registros ({bol_meta.age_str()})")
        st.caption(" · ".join(info_parts))

    st.divider()

    # ── Threshold controls ───────────────────────────────────────
    col_t1, col_t2, col_t3 = st.columns(3)
    with col_t1:
        threshold_faltas = st.slider(
            "% de faltas para alerta",
            min_value=10, max_value=50, value=25, step=5,
            key="threshold_faltas",
        )
    with col_t2:
        threshold_nota = st.slider(
            "Nota minima",
            min_value=3.0, max_value=8.0, value=6.0, step=0.5,
            key="threshold_nota",
        )
    with col_t3:
        min_disc = st.slider(
            "Min. disciplinas com nota baixa",
            min_value=2, max_value=6, value=3, step=1,
            key="min_disc_risco",
        )

    # ── Run analysis ─────────────────────────────────────────────
    risco_df = detect_risco_evasao(
        freq_df, boletim_df,
        threshold_faltas_pct=float(threshold_faltas),
        threshold_nota_min=float(threshold_nota),
        min_disciplinas_risco=int(min_disc),
    )

    if risco_df.empty:
        st.success("Nenhum aluno em risco com os parametros atuais.")
        return

    # ── Risk metrics ─────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    alto = len(risco_df[risco_df["nivel_risco"] == "ALTO"])
    medio = len(risco_df[risco_df["nivel_risco"] == "MEDIO"])
    baixo = len(risco_df[risco_df["nivel_risco"] == "BAIXO"])
    total = risco_df["id_aluno"].nunique()

    c1.metric("🔴 Risco Alto", alto)
    c2.metric("🟡 Risco Medio", medio)
    c3.metric("🟢 Risco Baixo", baixo)
    c4.metric("Total alunos em risco", total)

    st.divider()

    # ── Risk breakdown charts ─────────────────────────────────────
    col_chart, col_tipo_chart = st.columns(2)
    with col_chart:
        nivel_counts = risco_df.groupby("nivel_risco").size().reset_index(name="Quantidade")
        st.caption("Distribuicao por nivel de risco")
        st.bar_chart(nivel_counts.set_index("nivel_risco")["Quantidade"])
    with col_tipo_chart:
        tipo_counts = risco_df.groupby("tipo_risco").size().reset_index(name="Quantidade")
        st.caption("Distribuicao por tipo de risco")
        st.bar_chart(tipo_counts.set_index("tipo_risco")["Quantidade"])

    st.divider()

    # ── Filters ──────────────────────────────────────────────────
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        tipos = ["Todos"] + list(risco_df["tipo_risco"].unique())
        selected_tipo = st.selectbox("Tipo de risco:", tipos, key="risco_tipo_filter")
    with col_f2:
        niveis = ["Todos", "ALTO", "MEDIO", "BAIXO"]
        selected_nivel = st.selectbox("Nivel:", niveis, key="risco_nivel_filter")

    display_df = risco_df.copy()
    if selected_tipo != "Todos":
        display_df = display_df[display_df["tipo_risco"] == selected_tipo]
    if selected_nivel != "Todos":
        display_df = display_df[display_df["nivel_risco"] == selected_nivel]

    # Show relevant columns
    show_cols = [c for c in [
        "id_aluno", "nome_aluno", "turma", "tipo_risco",
        "nivel_risco", "detalhes", "acao_sugerida",
    ] if c in display_df.columns]

    st.dataframe(
        display_df[show_cols] if show_cols else display_df,
        use_container_width=True,
        hide_index=True,
    )

    download_section("Farol de Risco", df=risco_df, filename_prefix="farol_risco")


# ═══════════════════════════════════════════════════════════════════
# Tab: Auditoria de Diarios
# ═══════════════════════════════════════════════════════════════════

def _render_auditoria_diarios():
    """Teacher diary compliance audit."""
    from services.pedagogico import (
        fetch_diarios_completos,
        audit_diarios_docentes,
        compute_compliance_by_turma,
    )

    st.subheader("Auditoria de Diarios — Engajamento Docente")
    st.caption(
        "Verifica quais diarios estao sem marcacao de frequencia recente "
        "e quais turmas/disciplinas tem lancamentos pendentes."
    )

    client = require_client()
    store = get_cache_store()

    # ── Load controls ────────────────────────────────────────────
    col_load, col_info = st.columns([1, 3])
    with col_load:
        if st.button(
            "📥 Carregar / Atualizar diarios",
            key="btn_load_diarios",
            use_container_width=True,
        ):
            st.session_state["_diarios_force_refresh"] = True

    force = st.session_state.pop("_diarios_force_refresh", False)
    diarios_df = st.session_state.get("ped_diarios_df", pd.DataFrame())

    if force or diarios_df.empty:
        if force:
            try:
                turmas = lista_turmas(client)
                turmas_ids = [t.get("id") for t in turmas if t.get("id") is not None]

                if not turmas_ids:
                    st.warning("Nenhuma turma encontrada.")
                    return

                diarios_df, diarios_meta = fetch_diarios_completos(
                    client, store, turmas_ids,
                    force_refresh=force,
                )
                st.session_state["ped_diarios_df"] = diarios_df
                st.session_state["ped_diarios_meta"] = diarios_meta

            except Exception as e:
                st.error(f"Erro ao carregar diarios: {e}")
                return

    if diarios_df.empty:
        with col_info:
            st.info("Clique em **Carregar diarios** para baixar os dados da API.")
        return

    diarios_meta = st.session_state.get("ped_diarios_meta")
    with col_info:
        if diarios_meta:
            st.caption(
                f"📝 {diarios_meta.rows} registros · "
                f"Atualizado ha {diarios_meta.age_str()}"
            )

    st.divider()

    # ── Run audit ────────────────────────────────────────────────
    audit_df = audit_diarios_docentes(diarios_df)

    if audit_df.empty:
        st.success("Todos os diarios estao em dia!")
        return

    # ── Metrics ──────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    pendentes = len(audit_df[audit_df["status"] == "Pendente"])
    atencao = len(audit_df[audit_df["status"] == "Atencao"])
    c1.metric("🔴 Pendentes", pendentes)
    c2.metric("🟡 Atencao", atencao)
    c3.metric("Total diarios analisados", len(audit_df))

    st.divider()

    # ── Pendentes table ──────────────────────────────────────────
    with st.expander(f"📋 Diarios pendentes ({pendentes})", expanded=True):
        pend_df = audit_df[audit_df["status"] == "Pendente"]
        if not pend_df.empty:
            st.dataframe(pend_df, use_container_width=True, hide_index=True)
        else:
            st.caption("Nenhum diario pendente.")

    with st.expander(f"⚠️ Diarios com atencao ({atencao})"):
        att_df = audit_df[audit_df["status"] == "Atencao"]
        if not att_df.empty:
            st.dataframe(att_df, use_container_width=True, hide_index=True)
        else:
            st.caption("Nenhum diario requer atencao.")

    # ── Compliance by turma ──────────────────────────────────────
    st.divider()
    st.subheader("Compliance por Turma")
    compliance = compute_compliance_by_turma(audit_df)
    if not compliance.empty:
        st.dataframe(compliance, use_container_width=True, hide_index=True)
    else:
        st.caption("Sem dados de compliance.")

    st.divider()
    download_section("Auditoria Diarios", df=audit_df, filename_prefix="auditoria_diarios")


# ═══════════════════════════════════════════════════════════════════
# Tab: Consulta Boletim
# ═══════════════════════════════════════════════════════════════════

def _render_consulta_boletim():
    """Individual student report card lookup."""
    st.subheader("Consulta de Boletim")

    boletim_df = st.session_state.get("ped_boletim_df", pd.DataFrame())

    if boletim_df.empty:
        st.info(
            "Os dados de boletim ainda nao foram carregados. "
            "Use a aba **Farol de Risco** para carregar os dados pedagogicos primeiro, "
            "ou consulte o endpoint via Explorer API."
        )
        return

    if "id_aluno" not in boletim_df.columns:
        st.warning("Coluna 'id_aluno' nao encontrada nos dados de boletim.")
        return

    # ── Student selector ─────────────────────────────────────────
    alunos_ids = sorted(boletim_df["id_aluno"].unique())

    # Build label map
    nome_col = None
    for c in ["nome_aluno", "nome", "nome_completo"]:
        if c in boletim_df.columns:
            nome_col = c
            break

    if nome_col:
        labels = {}
        for aid in alunos_ids:
            nome = boletim_df.loc[boletim_df["id_aluno"] == aid, nome_col].iloc[0] if len(
                boletim_df[boletim_df["id_aluno"] == aid]) > 0 else str(aid)
            labels[aid] = f"{nome} (ID: {aid})"
        selected = st.selectbox(
            "Selecionar aluno:",
            alunos_ids,
            format_func=lambda x: labels.get(x, str(x)),
            key="boletim_aluno_select",
        )
    else:
        selected = st.selectbox("Selecionar aluno (ID):", alunos_ids, key="boletim_aluno_select")

    if selected is not None:
        aluno_data = boletim_df[boletim_df["id_aluno"] == selected]

        if aluno_data.empty:
            st.warning("Sem dados de boletim para este aluno.")
            return

        # Show relevant columns
        display_cols = [c for c in aluno_data.columns
                        if c not in ["id_aluno", "_id_aluno_fetch"] and not c.startswith("_")]
        if display_cols:
            st.dataframe(aluno_data[display_cols], use_container_width=True, hide_index=True)
        else:
            st.dataframe(aluno_data, use_container_width=True, hide_index=True)

        download_section(
            f"Boletim {selected}",
            df=aluno_data,
            filename_prefix=f"boletim_{selected}",
        )
