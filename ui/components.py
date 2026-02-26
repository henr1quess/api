"""Shared Streamlit UI components."""

from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from services.cache_store import CacheStore, DatasetMeta
from services.export_utils import df_to_csv_bytes, df_to_excel_bytes, to_json_bytes


# ═══════════════════════════════════════════════════════════════════
# Singletons / session helpers
# ═══════════════════════════════════════════════════════════════════

def require_client():
    """Return the API client from session state, or show error and stop."""
    client = st.session_state.get("client")
    if client is None:
        st.warning("Configure o token da API na barra lateral para continuar.")
        st.stop()
    return client


def get_cache_store() -> CacheStore:
    """Return a singleton CacheStore."""
    if "cache_store" not in st.session_state:
        st.session_state["cache_store"] = CacheStore()
    return st.session_state["cache_store"]


def _token_for_key() -> str:
    """Extract the auth header for hashing (never stored in plain text)."""
    client = st.session_state.get("client")
    if client:
        return client._session.headers.get("Authorization", "")
    return ""


# ═══════════════════════════════════════════════════════════════════
# Cache-aware data fetcher
# ═══════════════════════════════════════════════════════════════════

def cached_fetch(
    endpoint_name: str,
    endpoint_path: str,
    fetch_fn: Callable[[], List[Dict]],
    params: Optional[Dict] = None,
    ttl_hours: Optional[float] = None,
    st_key: str = "",
) -> Tuple[Optional[pd.DataFrame], Optional[DatasetMeta]]:
    """Fetch data with cache support and Streamlit refresh buttons.

    Shows cache status (hit/miss, age, rows) and Atualizar button.
    Returns (df, meta) or (None, None) if no data.
    """
    store = get_cache_store()
    client = require_client()

    key = store.make_key(client.base_url, endpoint_path, params, _token_for_key())

    # Check if a refresh was requested
    refresh_flag = f"_refresh_{st_key or endpoint_name}"
    force = st.session_state.pop(refresh_flag, False)

    try:
        df, meta, hit = store.get_dataset(
            key=key,
            endpoint=endpoint_name,
            params=params,
            fetch_fn=fetch_fn,
            ttl_hours=ttl_hours,
            force_refresh=force,
        )
    except Exception as exc:
        st.error(f"Erro ao buscar {endpoint_name}: {exc}")
        return None, None

    # Show cache status
    show_cache_info(meta, hit, refresh_flag, st_key or endpoint_name)

    return df, meta


def show_cache_info(
    meta: DatasetMeta,
    cache_hit: bool,
    refresh_flag: str = "",
    st_key: str = "",
):
    """Render cache status bar with refresh button."""
    cols = st.columns([4, 1])
    with cols[0]:
        status = "Cache" if cache_hit else "API"
        fresh = "fresco" if meta.is_fresh() else "expirado"
        icon = "💾" if cache_hit else "🌐"
        st.caption(
            f"{icon} **{status}** ({fresh}) · "
            f"{meta.rows} registros · "
            f"Atualizado ha {meta.age_str()} · "
            f"TTL {meta.ttl_hours}h"
        )
    with cols[1]:
        if st.button("🔄 Atualizar", key=f"btn_refresh_{st_key}"):
            st.session_state[refresh_flag] = True
            st.rerun()


# ═══════════════════════════════════════════════════════════════════
# Turma / Diario helpers
# ═══════════════════════════════════════════════════════════════════

def format_turma_label(t: dict) -> str:
    """Build a readable label from a turma dict.

    lista_turmas uses 'nome', acesso_alunos uses 'nome_turma'.
    """
    nome = (
        t.get("nome_turma_completo")
        or t.get("nome_turma")
        or t.get("nome")
        or f"ID {t.get('id', '?')}"
    )
    curso = t.get("curso_nome", "")
    serie = t.get("serie_nome", "")
    tid = t.get("id", "")
    if curso and serie:
        return f"{curso} / {serie} / {nome} (ID: {tid})"
    return f"{nome} (ID: {tid})"


def parse_diarios(diarios_data: List[Dict]) -> Tuple[Dict[int, str], Dict[int, str]]:
    """Extract discipline and fase maps from diarios response.

    The diarios endpoint returns FLAT fields:
        disciplina: int, nome_disciplina: str
        fase_nota: int, nome_fase: str
    NOT nested dicts.
    """
    disc_map: Dict[int, str] = {}
    fase_map: Dict[int, str] = {}

    for d in diarios_data:
        if not isinstance(d, dict):
            continue

        # Discipline: flat int field
        disc_id = d.get("disciplina")
        disc_nome = d.get("nome_disciplina", str(disc_id))
        if disc_id is not None:
            disc_map[int(disc_id)] = str(disc_nome)

        # Fase/nota: flat int field
        fase_id = d.get("fase_nota")
        fase_nome = d.get("nome_fase", str(fase_id))
        if fase_id is not None:
            fase_map[int(fase_id)] = str(fase_nome)

    return disc_map, fase_map


def format_diario_label(d: dict) -> str:
    """Build a label for a diario entry."""
    if not isinstance(d, dict):
        return str(d)
    did = d.get("id", "?")
    disc = d.get("nome_disciplina", "")
    fase = d.get("nome_fase", "")
    return f"{disc} / {fase} (ID: {did})"


# ═══════════════════════════════════════════════════════════════════
# Downloads
# ═══════════════════════════════════════════════════════════════════

def download_section(
    label: str,
    df: Optional[pd.DataFrame] = None,
    json_data=None,
    filename_prefix: str = "export",
    excel_sheets: Optional[Dict[str, pd.DataFrame]] = None,
):
    """Render download buttons for CSV, Excel, and/or JSON."""
    cols = st.columns(3)

    if df is not None and not df.empty:
        with cols[0]:
            st.download_button(
                f"CSV – {label}",
                data=df_to_csv_bytes(df),
                file_name=f"{filename_prefix}.csv",
                mime="text/csv",
            )
        with cols[1]:
            sheets = excel_sheets or {label: df}
            st.download_button(
                f"Excel – {label}",
                data=df_to_excel_bytes(sheets),
                file_name=f"{filename_prefix}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    if json_data is not None:
        with cols[2]:
            st.download_button(
                f"JSON – {label}",
                data=to_json_bytes(json_data),
                file_name=f"{filename_prefix}.json",
                mime="application/json",
            )


# ═══════════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════════

def show_validation_summary(df: pd.DataFrame):
    """Show a colored summary of validation results."""
    if "_status" not in df.columns:
        return

    ok = int((df["_status"] == "OK").sum())
    warn = int((df["_status"] == "WARN").sum())
    erro = int((df["_status"] == "ERRO").sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("OK", ok)
    c2.metric("WARN", warn)
    c3.metric("ERRO", erro)

    if erro > 0:
        with st.expander(f"Ver {erro} erros", expanded=True):
            err_cols = [c for c in ("matricula", "_status", "_msg") if c in df.columns]
            st.dataframe(
                df[df["_status"] == "ERRO"][err_cols],
                use_container_width=True,
            )
    if warn > 0:
        with st.expander(f"Ver {warn} avisos"):
            warn_cols = [c for c in ("matricula", "_status", "_msg") if c in df.columns]
            st.dataframe(
                df[df["_status"] == "WARN"][warn_cols],
                use_container_width=True,
            )


def loading(msg: str = "Carregando dados..."):
    """Context manager wrapper for st.spinner."""
    return st.spinner(msg)
