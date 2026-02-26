"""Home page – connection test, cache overview."""

import streamlit as st

from ui.components import get_cache_store, require_client


def render():
    st.title("CEC – Painel SigaWeb")
    st.markdown(
        """
        Painel de automacao escolar integrado com a **ActiveSoft SigaWeb API**.

        **Funcionalidades:**
        - **Importar Notas** – carregar CSV de notas e simular envio
        - **Frequencia – Consulta** – consultar e exportar dados de frequencia
        - **Frequencia – Marcacao** – simular marcacao via CSV
        - **Explorer de Dados** – consultar qualquer endpoint GET
        - **Auditoria** – visualizar logs de acoes

        > Operacoes de escrita (POST) estao em **modo simulacao**.
        """
    )

    st.divider()

    # ── Connection test ──────────────────────────────────────────
    if st.button("Testar conexao com a API"):
        client = require_client()
        with st.spinner("Testando conexao..."):
            result = client.test_connection()
        if result["ok"]:
            st.success(f"Conexao OK – {result['count']} alunos ativos.")
        else:
            st.error(f"Falha: {result['error']}")

    st.divider()

    # ── Cache overview ───────────────────────────────────────────
    st.subheader("Cache de dados")

    store = get_cache_store()
    datasets = store.list_datasets()

    if not datasets:
        st.info("Nenhum dataset em cache. Navegue pelas telas para popular o cache.")
    else:
        st.caption(f"{len(datasets)} dataset(s) em cache.")
        for ds in datasets:
            fresh = "🟢" if ds.is_fresh() else "🟡"
            st.markdown(
                f"{fresh} **{ds.endpoint}** · "
                f"{ds.rows} registros · "
                f"Atualizado ha {ds.age_str()} · "
                f"TTL {ds.ttl_hours}h"
            )

        st.divider()
        if st.button("🗑️ Limpar todo o cache", type="secondary"):
            store.clear()
            st.success("Cache limpo.")
            st.rerun()
