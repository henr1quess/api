"""Home page – connection test, cache overview, and module summary."""

import streamlit as st

from ui.components import get_cache_store, require_client


def render():
    st.title("CEC – Painel SigaWeb")
    st.caption("Automacao escolar integrada com a ActiveSoft SigaWeb API v0")

    # ── Module overview ───────────────────────────────────────────
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
**💰 Financeiro**
- KPIs executivos (receita, inadimplencia)
- Aging da carteira com grafico
- Deteccao de inconsistencias financeiras
- Operacoes adversas (cancelados, estornados)
- Exportacao Excel multitabas
""")

    with col2:
        st.markdown("""
**🎓 Academico**
- Consulta de frequencia por diario
- Farol de Risco (faltas + notas criticas)
- Auditoria de diarios docentes
- Consulta de boletim individual
""")

    with col3:
        st.markdown("""
**⚙️ Operacoes / Explorer**
- Importacao de notas via CSV (simulacao)
- Marcacao de frequencia via CSV (simulacao)
- Explorer de qualquer endpoint GET
- Auditoria de acoes
""")

    st.caption(
        "Operacoes de escrita (POST) estao em **modo simulacao** — "
        "nenhum dado e enviado sem ativacao do WRITE_MODE_ENABLED."
    )

    st.divider()

    # ── Connection test ──────────────────────────────────────────
    col_btn, col_result = st.columns([1, 3])
    with col_btn:
        test = st.button("🔌 Testar conexao", use_container_width=True)
    if test:
        client = require_client()
        with st.spinner("Testando..."):
            result = client.test_connection()
        with col_result:
            if result["ok"]:
                st.success(f"Conexao OK – {result['count']} alunos ativos na API.")
            else:
                st.error(f"Falha: {result['error']}")

    st.divider()

    # ── Cache overview ───────────────────────────────────────────
    st.subheader("Cache de dados em disco")

    store = get_cache_store()
    datasets = store.list_datasets()

    if not datasets:
        st.info(
            "Nenhum dataset em cache. "
            "Navegue pelas telas Financeiro e Academico para popular o cache."
        )
    else:
        fresh = sum(1 for ds in datasets if ds.is_fresh())
        total_rows = sum(ds.rows for ds in datasets)

        m1, m2, m3 = st.columns(3)
        m1.metric("Datasets em cache", len(datasets))
        m2.metric("Atualizados (TTL ok)", fresh)
        m3.metric("Registros totais", f"{total_rows:,}")

        st.divider()

        for ds in datasets:
            icon = "🟢" if ds.is_fresh() else "🟡"
            st.markdown(
                f"{icon} **{ds.endpoint}** · "
                f"{ds.rows:,} registros · "
                f"Atualizado ha {ds.age_str()} · "
                f"TTL {ds.ttl_hours}h"
            )

        st.divider()
        col_clear, _ = st.columns([1, 3])
        with col_clear:
            if st.button("🗑️ Limpar todo o cache", type="secondary", use_container_width=True):
                store.clear()
                st.success("Cache limpo.")
                st.rerun()
