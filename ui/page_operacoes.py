"""Operations page — 2 tabs for data entry workflows.

Tabs: Importar Notas | Frequencia – Marcacao
"""

import streamlit as st

from ui import page_grades, page_freq_mark


def render():
    st.title("⚙️ Operacoes")

    tab_notas, tab_freq = st.tabs([
        "📝 Importar Notas",
        "📌 Frequencia – Marcacao",
    ])

    with tab_notas:
        page_grades.render()

    with tab_freq:
        page_freq_mark.render()
