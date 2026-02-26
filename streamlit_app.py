"""CEC – Painel SigaWeb.

Streamlit application for school automation
integrating with ActiveSoft SigaWeb API v0.

Run: streamlit run streamlit_app.py
"""

import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# ── Ensure project root is on sys.path ───────────────────────────
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from activesoft_client import ActiveSoftClient  # noqa: E402
from ui import page_home, page_grades, page_freq_query, page_freq_mark, page_explorer, page_audit  # noqa: E402

# ── Page config ──────────────────────────────────────────────────
st.set_page_config(
    page_title="CEC – Painel SigaWeb",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ──────────────────────────────────────────────────────
with st.sidebar:
    st.title("🏫 CEC Painel")
    st.caption("Automacao escolar – SigaWeb API")
    st.divider()

    # Credentials
    base_url = st.text_input(
        "URL Base",
        value=os.getenv("ERP_BASE_URL", "https://siga.activesoft.com.br"),
    )
    token = st.text_input(
        "Token da API",
        type="password",
        value=os.getenv("ERP_TOKEN", ""),
    )

    if token and base_url:
        # Only create a new client if inputs changed
        key = f"{base_url}|{token}"
        if st.session_state.get("_client_key") != key:
            st.session_state["client"] = ActiveSoftClient(base_url, token)
            st.session_state["_client_key"] = key
        st.success("Conectado", icon="✅")
    else:
        st.session_state.pop("client", None)
        st.warning("Insira o token para comecar.")

    st.divider()

    # Navigation
    PAGES = {
        "🏠 Inicio": "home",
        "📝 Importar Notas": "grades",
        "📋 Frequencia – Consulta": "freq_query",
        "📌 Frequencia – Marcacao": "freq_mark",
        "🔍 Explorer de Dados": "explorer",
        "📊 Auditoria": "audit",
    }

    page = st.radio("Navegacao", list(PAGES.keys()), label_visibility="collapsed")

    st.divider()
    write_mode = os.getenv("WRITE_MODE_ENABLED", "false").lower() == "true"
    if write_mode:
        st.error("⚠️ MODO ESCRITA ATIVO")
    else:
        st.info("🔒 Modo leitura (POST bloqueado)")

# ── Routing ──────────────────────────────────────────────────────
page_key = PAGES.get(page, "home")

if page_key == "home":
    page_home.render()
elif page_key == "grades":
    page_grades.render()
elif page_key == "freq_query":
    page_freq_query.render()
elif page_key == "freq_mark":
    page_freq_mark.render()
elif page_key == "explorer":
    page_explorer.render()
elif page_key == "audit":
    page_audit.render()
