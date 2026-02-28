"""Financial dashboard page — 5 tabs.

Tabs: Executivo | Cobranca | Inconsistencias | Operacoes Adversas | Exportacoes
"""

import streamlit as st

from ui.components import (
    require_client,
    get_cache_store,
    download_section,
)
from services.finances import (
    fetch_all_boletos,
    build_financial_dataset,
    detect_inconsistencies,
    detect_adverse_operations,
    compute_kpis,
    top_servicos,
    mix_forma_recebimento,
    build_export_package,
)
from services.export_utils import df_to_excel_bytes
from activesoft_client.endpoints import (
    lista_alunos,
    financeiro_servicos,
    acesso_alunos,
)
import pandas as pd


def render():
    st.title("💰 Financeiro")

    client = require_client()
    store = get_cache_store()

    # ── Load base data (students + services) ─────────────────────
    @st.cache_data(ttl=3600, show_spinner=False)
    def _load_alunos():
        return lista_alunos(client)

    @st.cache_data(ttl=3600, show_spinner=False)
    def _load_alunos_ativos():
        return acesso_alunos(client)

    @st.cache_data(ttl=3600, show_spinner=False)
    def _load_servicos():
        return financeiro_servicos(client)

    # ── Session state for financial data ─────────────────────────
    if "fin_df" not in st.session_state:
        st.session_state["fin_df"] = pd.DataFrame()
    if "fin_meta" not in st.session_state:
        st.session_state["fin_meta"] = None

    # ── Tabs ─────────────────────────────────────────────────────
    tab_exec, tab_cobr, tab_incon, tab_adv, tab_export = st.tabs([
        "📊 Executivo",
        "📋 Cobranca",
        "⚠️ Inconsistencias",
        "🚨 Operacoes Adversas",
        "📥 Exportacoes",
    ])

    # ── Data loading controls (shared across tabs) ───────────────
    with tab_exec:
        _render_executivo(client, store)

    with tab_cobr:
        _render_cobranca()

    with tab_incon:
        _render_inconsistencias(client)

    with tab_adv:
        _render_adversas()

    with tab_export:
        _render_exportacoes(client)


# ═══════════════════════════════════════════════════════════════════
# Tab renderers
# ═══════════════════════════════════════════════════════════════════

def _render_executivo(client, store):
    """Executive dashboard with KPIs."""
    st.subheader("Dashboard Executivo")

    col_load, col_info = st.columns([1, 3])
    with col_load:
        if st.button("📥 Carregar boletos 2026", key="btn_load_boletos"):
            st.session_state["_fin_force_refresh"] = True

        if st.button("🔄 Atualizar dados", key="btn_refresh_boletos"):
            st.session_state["_fin_force_refresh"] = True

    # Load data
    force = st.session_state.pop("_fin_force_refresh", False)
    fin_df = st.session_state.get("fin_df", pd.DataFrame())
    fin_meta = st.session_state.get("fin_meta")

    if force or fin_df.empty:
        if force or fin_df.empty:
            try:
                alunos_ativos = acesso_alunos(client)
                alunos_ids = [a.get("id_aluno", a.get("id", a.get("aluno_id")))
                              for a in alunos_ativos if a.get("id_aluno") or a.get("id")]
                alunos_ids = [int(x) for x in alunos_ids if x is not None]

                if not alunos_ids:
                    st.warning("Nenhum aluno ativo encontrado.")
                    return

                boletos_df, meta = fetch_all_boletos(
                    client, store, alunos_ids,
                    ano=2026, force_refresh=force,
                )

                alunos_df = pd.DataFrame(lista_alunos(client))
                servicos_df = pd.DataFrame(financeiro_servicos(client))

                fin_df = build_financial_dataset(boletos_df, alunos_df, servicos_df)
                st.session_state["fin_df"] = fin_df
                st.session_state["fin_meta"] = meta
                fin_meta = meta
            except Exception as e:
                st.error(f"Erro ao carregar dados financeiros: {e}")
                return

    if fin_df.empty:
        with col_info:
            st.info("Clique em **Carregar boletos 2026** para baixar os dados da API.")
        return

    # Show cache info
    if fin_meta:
        with col_info:
            st.caption(
                f"📊 {len(fin_df)} registros · "
                f"Atualizado ha {fin_meta.age_str()} · "
                f"[dados de {fin_meta.timestamp_iso[:10]}]"
            )

    st.divider()

    # ── KPIs ─────────────────────────────────────────────────────
    # Month filter
    meses = sorted(fin_df["mes_competencia"].dropna().unique()) if "mes_competencia" in fin_df.columns else []
    selected_mes = st.selectbox("Filtrar por mes:", ["Todos"] + list(meses), key="fin_mes_filter")

    filtered = fin_df
    if selected_mes != "Todos" and "mes_competencia" in fin_df.columns:
        filtered = fin_df[fin_df["mes_competencia"] == selected_mes]

    kpis = compute_kpis(filtered)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Receita Prevista", f"R$ {kpis['receita_prevista']:,.2f}")
    c2.metric("Receita Recebida", f"R$ {kpis['receita_recebida']:,.2f}")
    c3.metric("Inadimplencia (R$)", f"R$ {kpis['inadimplencia_valor']:,.2f}")
    c4.metric("Inadimplencia (%)", f"{kpis['inadimplencia_pct']:.1f}%")

    st.divider()

    # ── Top servicos & mix ───────────────────────────────────────
    col_serv, col_mix = st.columns(2)
    with col_serv:
        st.subheader("Top 5 Servicos por Receita")
        ts = top_servicos(filtered)
        if not ts.empty:
            st.dataframe(ts, use_container_width=True, hide_index=True)
        else:
            st.caption("Sem dados de servicos.")

    with col_mix:
        st.subheader("Mix por Forma de Recebimento")
        mr = mix_forma_recebimento(filtered)
        if not mr.empty:
            st.dataframe(mr, use_container_width=True, hide_index=True)
        else:
            st.caption("Sem dados de forma de recebimento.")


def _render_cobranca():
    """Aging analysis and critical titles."""
    st.subheader("Painel de Cobranca")

    fin_df = st.session_state.get("fin_df", pd.DataFrame())
    if fin_df.empty:
        st.info("Carregue os dados financeiros na aba **Executivo** primeiro.")
        return

    # ── Filters ──────────────────────────────────────────────────
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        if "mes_competencia" in fin_df.columns:
            meses = ["Todos"] + sorted(fin_df["mes_competencia"].dropna().unique().tolist())
            mes_fil = st.selectbox("Mes:", meses, key="cobr_mes")
        else:
            mes_fil = "Todos"
    with col_f2:
        turma_col = next((c for c in ["nome_turma", "turma"] if c in fin_df.columns), None)
        if turma_col:
            turmas = ["Todas"] + sorted(fin_df[turma_col].dropna().unique().tolist())
            turma_fil = st.selectbox("Turma:", turmas, key="cobr_turma")
        else:
            turma_fil = "Todas"

    filtered = fin_df.copy()
    if mes_fil != "Todos" and "mes_competencia" in filtered.columns:
        filtered = filtered[filtered["mes_competencia"] == mes_fil]
    if turma_fil != "Todas" and turma_col:
        filtered = filtered[filtered[turma_col] == turma_fil]

    # ── Aging table + chart ───────────────────────────────────────
    if "aging_bucket" in filtered.columns:
        st.subheader("Aging da Carteira")

        # Find valor column (real API uses valor_documento)
        valor_col = next(
            (c for c in [
                "valor_documento", "valor_recebido_total",
                "valor", "valor_nominal", "valor_titulo", "vlr_nominal",
            ] if c in filtered.columns),
            None,
        )

        if valor_col:
            aging = filtered.groupby("aging_bucket", observed=True).agg(
                Quantidade=("aging_bucket", "count"),
                **{"Valor Total (R$)": (valor_col, lambda x: pd.to_numeric(x, errors="coerce").sum())},
            ).reset_index()
            aging.columns = ["Faixa", "Quantidade", "Valor Total (R$)"]
        else:
            aging = filtered["aging_bucket"].value_counts().reset_index()
            aging.columns = ["Faixa", "Quantidade"]
            aging["Valor Total (R$)"] = 0.0

        col_tbl, col_chart = st.columns([1, 1])
        with col_tbl:
            st.dataframe(aging, use_container_width=True, hide_index=True)
        with col_chart:
            st.bar_chart(aging.set_index("Faixa")["Quantidade"], use_container_width=True)

    st.divider()

    # ── Critical titles ──────────────────────────────────────────
    if "dias_atraso" in filtered.columns:
        inadimplentes = filtered[filtered["dias_atraso"] > 0]
        st.subheader(f"Titulos em Atraso ({len(inadimplentes)})")

        if inadimplentes.empty:
            st.success("Nenhum titulo em atraso nos filtros selecionados!")
        else:
            # Show top 50, sorted by overdue days
            criticos = inadimplentes.sort_values("dias_atraso", ascending=False).head(50)

            # Real API columns + derived columns
            show_cols = [c for c in [
                "nome_aluno", "aluno", "nome_turma", "turma",
                "dias_atraso", "aging_bucket",
                "valor_documento", "valor_recebido_total",
                "valor", "valor_nominal", "vlr_nominal",
                "mes_competencia",
                "situacao_titulo", "status", "situacao",
                "dt_vencimento", "data_vencimento",
            ] if c in criticos.columns]

            if show_cols:
                st.dataframe(criticos[show_cols], use_container_width=True, hide_index=True)
            else:
                st.dataframe(criticos, use_container_width=True, hide_index=True)

            download_section("Cobranca", df=inadimplentes, filename_prefix="cobranca_inadimplentes")


def _render_inconsistencias(client):
    """Financial inconsistency detection."""
    st.subheader("Deteccao de Inconsistencias")

    fin_df = st.session_state.get("fin_df", pd.DataFrame())
    if fin_df.empty:
        st.info("Carregue os dados financeiros na aba Executivo primeiro.")
        return

    # Get active student IDs
    try:
        alunos_ativos = acesso_alunos(client)
        alunos_ids = [a.get("id_aluno", a.get("id", a.get("aluno_id")))
                      for a in alunos_ativos if a.get("id_aluno") or a.get("id")]
        alunos_ids = [int(x) for x in alunos_ids if x is not None]
    except Exception:
        alunos_ids = []

    if st.button("🔍 Executar analise de inconsistencias", key="btn_run_inconsistencies"):
        with st.spinner("Analisando..."):
            result = detect_inconsistencies(fin_df, alunos_ids, ano=2026)
            st.session_state["fin_inconsistencies"] = result

    incon_df = st.session_state.get("fin_inconsistencies", pd.DataFrame())
    if incon_df.empty:
        st.info("Clique no botao acima para executar a analise.")
        return

    # ── Summary metrics ──────────────────────────────────────────
    total = len(incon_df)
    st.metric("Total de inconsistencias", total)

    for tipo in incon_df["tipo"].unique():
        subset = incon_df[incon_df["tipo"] == tipo]
        impacto = subset["valor_impacto"].sum()
        with st.expander(f"**{tipo}** — {len(subset)} ocorrencia(s) · R$ {impacto:,.2f}", expanded=True):
            st.dataframe(subset, use_container_width=True, hide_index=True)

    st.divider()

    # ── Export ────────────────────────────────────────────────────
    if not incon_df.empty:
        sheets = {}
        for tipo in incon_df["tipo"].unique():
            sheets[tipo] = incon_df[incon_df["tipo"] == tipo]
        st.download_button(
            "📥 Excel — Inconsistencias",
            data=df_to_excel_bytes(sheets),
            file_name="inconsistencias_financeiras.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


def _render_adversas():
    """Adverse operations detection."""
    st.subheader("Operacoes Adversas")

    fin_df = st.session_state.get("fin_df", pd.DataFrame())
    if fin_df.empty:
        st.info("Carregue os dados financeiros na aba Executivo primeiro.")
        return

    if st.button("🔍 Detectar operacoes adversas", key="btn_run_adverse"):
        with st.spinner("Analisando..."):
            result_df, warnings = detect_adverse_operations(fin_df)
            st.session_state["fin_adverse"] = result_df
            st.session_state["fin_adverse_warnings"] = warnings

    adv_df = st.session_state.get("fin_adverse", pd.DataFrame())
    warnings = st.session_state.get("fin_adverse_warnings", [])

    # ── Transparency warnings ────────────────────────────────────
    if warnings:
        st.info("**Transparencia — Limitacoes da deteccao via API:**")
        for w in warnings:
            st.caption(f"⚠️ {w}")
        st.divider()

    if adv_df.empty:
        if not warnings:
            st.info("Clique no botao acima para executar a analise.")
        else:
            st.success("Nenhuma operacao adversa detectada nos dados disponiveis.")
        return

    # ── Results by type ──────────────────────────────────────────
    for tipo in adv_df["tipo"].unique():
        subset = adv_df[adv_df["tipo"] == tipo]
        impacto = subset["valor_impacto"].sum()
        icon = {"CANCELADO": "❌", "ESTORNADO": "🔄", "BAIXA_RETROATIVA": "⏰"}.get(tipo, "⚠️")
        with st.expander(f"{icon} **{tipo}** — {len(subset)} ocorrencia(s) · R$ {impacto:,.2f}", expanded=True):
            st.dataframe(subset, use_container_width=True, hide_index=True)

    st.divider()
    download_section("Operacoes Adversas", df=adv_df, filename_prefix="operacoes_adversas")


def _render_exportacoes(client):
    """Monthly export package."""
    st.subheader("Pacote de Exportacao Financeira")

    fin_df = st.session_state.get("fin_df", pd.DataFrame())
    if fin_df.empty:
        st.info("Carregue os dados financeiros na aba Executivo primeiro.")
        return

    # Month filter
    meses = sorted(fin_df["mes_competencia"].dropna().unique()) if "mes_competencia" in fin_df.columns else []
    selected_mes = st.selectbox("Mes para exportacao:", ["Todos"] + list(meses), key="export_mes_filter")
    mes_filter = None if selected_mes == "Todos" else selected_mes

    # Get inconsistencies and adverse if computed
    incon_df = st.session_state.get("fin_inconsistencies", pd.DataFrame())
    adv_df = st.session_state.get("fin_adverse", pd.DataFrame())

    st.markdown("""
    O pacote Excel inclui as seguintes abas:
    1. **Resumo Executivo** — KPIs consolidados
    2. **Aging** — Faixas de vencimento
    3. **Inadimplentes** — Titulos em atraso
    4. **Inconsistencias** — Regras de validacao
    5. **Operacoes Adversas** — Cancelados, estornados, retroativas
    6. **Base Detalhada** — Todos os registros filtrados
    """)

    if st.button("📦 Gerar pacote Excel", key="btn_gen_package"):
        with st.spinner("Gerando pacote..."):
            sheets = build_export_package(fin_df, incon_df, adv_df, mes_filter=mes_filter)
            excel_bytes = df_to_excel_bytes(sheets)

            mes_label = selected_mes.replace("-", "_") if mes_filter else "completo"
            st.download_button(
                f"📥 Baixar pacote financeiro ({mes_label})",
                data=excel_bytes,
                file_name=f"pacote_financeiro_{mes_label}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
