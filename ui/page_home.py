"""Home page – connection test and overview."""

import streamlit as st

from ui.components import require_client


def render():
    st.title("CEC – Painel SigaWeb")
    st.markdown(
        """
        Bem-vindo ao painel de automacao escolar integrado com a **ActiveSoft SigaWeb API**.

        **Funcionalidades:**
        - **Importar Notas** – carregar CSV de notas e simular envio
        - **Frequencia – Consulta** – consultar e exportar dados de frequencia
        - **Frequencia – Marcacao** – simular marcacao via CSV
        - **Explorer de Dados** – consultar qualquer endpoint GET
        - **Auditoria** – visualizar logs de acoes

        > Todas as operacoes de escrita (POST) estao em **modo simulacao**.
        > Nenhum dado e enviado ao servidor sem autorizacao explicita.
        """
    )

    st.divider()

    if st.button("Testar conexao com a API"):
        client = require_client()
        with st.spinner("Testando conexao..."):
            result = client.test_connection()

        if result["ok"]:
            st.success(
                f"Conexao OK – {result['count']} alunos ativos encontrados."
            )
        else:
            st.error(f"Falha na conexao: {result['error']}")
