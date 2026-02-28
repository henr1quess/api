"""Financial analytics: boleto consolidation, inconsistencies, adverse operations.

Provides:
- Bulk fetch of boletos for all students (with progress tracking)
- Unified financial dataset (boletos x alunos x servicos)
- Inconsistency detection (regras de negocio confirmadas)
- Adverse operation detection (best-effort via API fields)

Real API field names (discovered via testing):
- titulo, dt_vencimento, dt_pagamento, dt_processamento
- valor_documento, valor_recebido_total
- situacao_titulo ("LIQ" = liquidado, "ABR" = aberto, etc.)
- nome_servico (e.g. "Mensalidade EF 4 Ano (S.A)")
- aluno (student name), turma (class name), aluno_matricula, pagador
"""

import logging
import time
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from services.cache_store import CacheStore, TTL_PERMANENT, DatasetMeta

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# Bulk fetch
# ═══════════════════════════════════════════════════════════════════

_FETCH_DELAY = 0.20  # seconds between API calls (slightly higher to avoid 403)
_PARTIAL_SAVE_INTERVAL = 50  # save partial results every N students


def fetch_all_boletos(
    client: Any,
    store: CacheStore,
    alunos_ids: List[int],
    ano: int = 2026,
    force_refresh: bool = False,
) -> Tuple[pd.DataFrame, Optional[DatasetMeta]]:
    """Fetch boletos for every student and return a consolidated DataFrame.

    Uses permanent cache -- only calls the API on first load or manual refresh.
    Shows st.progress() during fetch.

    Resilient design:
    - Catches errors per-student (never crashes the whole loop)
    - Saves partial results every 50 students
    - Saves final results even if some students failed
    - Retries are handled by http_client (429, 403, 5xx)
    """
    from activesoft_client.endpoints import informacoes_boleto

    cache_key = store.make_key(
        client.base_url,
        f"financeiro/boletos_consolidado_{ano}",
        {"ano": str(ano), "total_alunos": str(len(alunos_ids))},
        client._session.headers.get("Authorization", ""),
    )

    # Try cache first
    if not force_refresh:
        cached = store._load(cache_key)
        if cached is not None:
            return cached[0], cached[1]

    # Fetch from API
    all_records: List[Dict] = []
    progress = st.progress(0, text="Carregando boletos...")
    errors: List[str] = []
    consecutive_errors = 0

    for i, aluno_id in enumerate(alunos_ids):
        try:
            records = informacoes_boleto(client, id_aluno=aluno_id)
            if isinstance(records, list):
                for r in records:
                    r["_id_aluno_fetch"] = aluno_id
                all_records.extend(records)
            elif isinstance(records, dict):
                records["_id_aluno_fetch"] = aluno_id
                all_records.append(records)
            consecutive_errors = 0  # reset on success
        except Exception as e:
            errors.append(f"Aluno {aluno_id}: {e}")
            consecutive_errors += 1
            logger.warning("Boleto fetch error for aluno %s: %s", aluno_id, e)

            # If too many consecutive errors, the API might be rate-limiting hard
            # Wait longer before continuing
            if consecutive_errors >= 5:
                logger.warning(
                    "5 consecutive errors -- pausing 10s before continuing"
                )
                time.sleep(10.0)
                consecutive_errors = 0  # reset after long pause

        progress.progress(
            (i + 1) / len(alunos_ids),
            text=f"Carregando boletos: {i + 1}/{len(alunos_ids)} "
                 f"({len(all_records)} boletos encontrados)",
        )

        # Periodic partial save -- protect against crash/disconnect
        if (i + 1) % _PARTIAL_SAVE_INTERVAL == 0 and all_records:
            _save_partial(store, cache_key, all_records, ano, tag="parcial")

        if i < len(alunos_ids) - 1:
            time.sleep(_FETCH_DELAY)

    progress.empty()

    if errors:
        with st.expander(
            f"⚠️ {len(errors)} erro(s) ao buscar boletos "
            f"({len(all_records)} boletos salvos com sucesso)",
            expanded=False,
        ):
            for err in errors[:20]:
                st.caption(f"  - {err}")
            if len(errors) > 20:
                st.caption(f"  ... e mais {len(errors) - 20} erros.")

    # Always save -- even if some students failed
    df = pd.DataFrame(all_records) if all_records else pd.DataFrame()
    meta = store._save(
        cache_key,
        f"financeiro/boletos_consolidado_{ano}",
        {"ano": ano, "alunos_processados": len(alunos_ids), "erros": len(errors)},
        df,
        TTL_PERMANENT,
    )
    return df, meta


def _save_partial(
    store: CacheStore,
    cache_key: str,
    records: List[Dict],
    ano: int,
    tag: str = "parcial",
):
    """Save partial results to cache (overwriting previous partial)."""
    try:
        df = pd.DataFrame(records)
        store._save(
            cache_key,
            f"financeiro/boletos_consolidado_{ano}",
            {"ano": ano, "status": tag, "registros": len(records)},
            df,
            TTL_PERMANENT,
        )
    except Exception as e:
        logger.warning("Failed to save partial boleto data: %s", e)


# ═══════════════════════════════════════════════════════════════════
# Dataset builder
# ═══════════════════════════════════════════════════════════════════

def build_financial_dataset(
    boletos_df: pd.DataFrame,
    alunos_df: pd.DataFrame,
    servicos_df: pd.DataFrame,
) -> pd.DataFrame:
    """Join boletos with student and service data, add derived columns.

    Returns enriched DataFrame with aging_bucket, dias_atraso, diferenca_valor.
    Adapts to whatever columns the API actually provides.

    Real API boleto fields include:
    - aluno (student name), turma (class name), aluno_matricula, pagador
    - valor_documento, valor_recebido_total, situacao_titulo
    - dt_vencimento, dt_pagamento, dt_processamento, nome_servico
    """
    if boletos_df.empty:
        return boletos_df

    df = boletos_df.copy()

    # ── Identify key columns (API field names may vary) ──────────
    id_aluno_col = _find_column(df, [
        "_id_aluno_fetch", "id_aluno", "aluno_id",
    ])
    valor_nominal_col = _find_column(df, [
        "valor_documento", "valor", "valor_nominal", "valor_titulo", "vlr_nominal",
    ])
    valor_pago_col = _find_column(df, [
        "valor_recebido_total", "valor_pago", "vlr_pago", "valor_recebido",
    ])
    vencimento_col = _find_column(df, [
        "dt_vencimento", "data_vencimento", "vencimento",
    ])
    pagamento_col = _find_column(df, [
        "dt_pagamento", "data_pagamento", "data_liquidacao",
    ])
    status_col = _find_column(df, [
        "situacao_titulo", "status", "situacao", "status_titulo",
    ])
    servico_col = _find_column(df, [
        "nome_servico", "servico", "descricao_servico", "id_servico",
    ])
    competencia_col = _find_column(df, [
        "competencia", "mes_competencia", "referencia", "mes_referencia",
    ])
    # The boleto data already has student name and turma as fields
    nome_aluno_col = _find_column(df, ["aluno", "nome_aluno", "nome"])
    turma_col = _find_column(df, ["turma", "nome_turma"])

    # ── Ensure nome_aluno and nome_turma columns are present ─────
    if nome_aluno_col and nome_aluno_col != "nome_aluno":
        df["nome_aluno"] = df[nome_aluno_col]
    if turma_col and turma_col != "nome_turma":
        df["nome_turma"] = df[turma_col]

    # ── Join with alunos (nome, turma) only if not already in data ──
    if "nome_aluno" not in df.columns and id_aluno_col and not alunos_df.empty:
        aluno_id_col_alunos = _find_column(alunos_df, ["id_aluno", "id", "aluno_id"])
        aluno_nome_col = _find_column(alunos_df, ["nome", "nome_aluno", "nome_completo"])
        if aluno_id_col_alunos and aluno_nome_col:
            alunos_slim = alunos_df[[aluno_id_col_alunos, aluno_nome_col]].drop_duplicates()
            alunos_slim = alunos_slim.rename(columns={
                aluno_id_col_alunos: "_join_id_aluno",
                aluno_nome_col: "nome_aluno",
            })
            df["_join_id_aluno"] = df[id_aluno_col]
            df = df.merge(alunos_slim, on="_join_id_aluno", how="left")
            df.drop(columns=["_join_id_aluno"], inplace=True)

    # ── Derived: dias_atraso ─────────────────────────────────────
    if vencimento_col:
        df["_dt_vencimento"] = pd.to_datetime(df[vencimento_col], errors="coerce")
        today = pd.Timestamp(date.today())
        df["dias_atraso"] = (today - df["_dt_vencimento"]).dt.days

        # Only count as overdue if not paid
        if pagamento_col:
            df["_dt_pagamento"] = pd.to_datetime(df[pagamento_col], errors="coerce")
            paid_mask = df["_dt_pagamento"].notna()
            df.loc[paid_mask, "dias_atraso"] = 0
        elif status_col:
            # situacao_titulo: "LIQ" = liquidado (paid)
            paid_statuses = ["liq", "pago", "liquidado", "recebido", "baixado"]
            paid_mask = df[status_col].astype(str).str.lower().str.strip().isin(paid_statuses)
            df.loc[paid_mask, "dias_atraso"] = 0

        df["dias_atraso"] = df["dias_atraso"].clip(lower=0)

    # ── Derived: aging_bucket ────────────────────────────────────
    if "dias_atraso" in df.columns:
        df["aging_bucket"] = pd.cut(
            df["dias_atraso"],
            bins=[-1, 0, 30, 60, 90, 999999],
            labels=["Em dia", "1-30", "31-60", "61-90", ">90"],
        )

    # ── Derived: diferenca_valor ─────────────────────────────────
    if valor_nominal_col and valor_pago_col:
        df["_vn"] = pd.to_numeric(df[valor_nominal_col], errors="coerce")
        df["_vp"] = pd.to_numeric(df[valor_pago_col], errors="coerce")
        df["diferenca_valor"] = df["_vp"] - df["_vn"]
        df.drop(columns=["_vn", "_vp"], inplace=True)

    # ── Derived: mes_competencia ─────────────────────────────────
    if competencia_col:
        df["mes_competencia"] = df[competencia_col].astype(str)
    elif vencimento_col and "_dt_vencimento" in df.columns:
        df["mes_competencia"] = df["_dt_vencimento"].dt.strftime("%Y-%m")

    # Cleanup temp columns
    for c in ["_dt_vencimento", "_dt_pagamento"]:
        if c in df.columns:
            df.drop(columns=[c], inplace=True)

    return df


# ═══════════════════════════════════════════════════════════════════
# Inconsistency detection
# ═══════════════════════════════════════════════════════════════════

def detect_inconsistencies(
    df: pd.DataFrame,
    alunos_ativos_ids: List[int],
    alunos_nomes: Optional[Dict[int, str]] = None,
    ano: int = 2026,
) -> pd.DataFrame:
    """Detect financial inconsistencies based on confirmed business rules.

    Rules:
    1. VALOR_DIVERGENTE: valor_pago != valor_nominal (where paid)
    2. MES_SEM_BOLETO: active student missing boleto for a past month in {ano}
    3. SEM_MENSALIDADE: active student without any service matching 'Mens%'

    Returns DataFrame with: id_aluno, nome_aluno, tipo, descricao, valor_impacto
    """
    results: List[Dict] = []
    alunos_nomes = alunos_nomes or {}

    if df.empty:
        return pd.DataFrame(results)

    id_aluno_col = _find_column(df, ["_id_aluno_fetch", "id_aluno", "aluno_id"])
    valor_nominal_col = _find_column(df, [
        "valor_documento", "valor", "valor_nominal", "valor_titulo", "vlr_nominal",
    ])
    valor_pago_col = _find_column(df, [
        "valor_recebido_total", "valor_pago", "vlr_pago", "valor_recebido",
    ])
    status_col = _find_column(df, [
        "situacao_titulo", "status", "situacao", "status_titulo",
    ])
    servico_col = _find_column(df, [
        "nome_servico", "servico", "descricao_servico",
    ])
    nome_aluno_boleto_col = _find_column(df, ["nome_aluno", "aluno", "nome"])

    # Build a name lookup from boleto data + provided mapping
    _nome_map: Dict[Any, str] = dict(alunos_nomes)
    if id_aluno_col and nome_aluno_boleto_col:
        for _, row in df[[id_aluno_col, nome_aluno_boleto_col]].drop_duplicates().iterrows():
            aid = row[id_aluno_col]
            name = row[nome_aluno_boleto_col]
            if aid and name and str(name).strip():
                _nome_map[aid] = str(name).strip()

    def _get_name(aid):
        return _nome_map.get(aid, str(aid))

    # ── Rule 1: VALOR_DIVERGENTE ─────────────────────────────────
    if valor_nominal_col and valor_pago_col and status_col:
        # situacao_titulo "LIQ" means paid/liquidated
        paid_statuses = ["liq", "pago", "liquidado", "recebido", "baixado"]
        mask_paid = df[status_col].astype(str).str.lower().str.strip().isin(paid_statuses)
        vn = pd.to_numeric(df[valor_nominal_col], errors="coerce")
        vp = pd.to_numeric(df[valor_pago_col], errors="coerce")
        mask_diff = (mask_paid) & (vn.notna()) & (vp.notna()) & ((vp - vn).abs() > 0.01)

        for _, row in df[mask_diff].iterrows():
            diff = float(vp[row.name] - vn[row.name])
            direction = "a mais" if diff > 0 else "a menos"
            aid = row.get(id_aluno_col, "") if id_aluno_col else ""
            results.append({
                "id_aluno": aid,
                "nome_aluno": _get_name(aid),
                "tipo": "VALOR_DIVERGENTE",
                "descricao": f"Pago R$ {direction}: diferenca de R$ {abs(diff):.2f}",
                "valor_impacto": round(abs(diff), 2),
            })

    # ── Rule 2: MES_SEM_BOLETO ───────────────────────────────────
    if id_aluno_col and "mes_competencia" in df.columns:
        today = date.today()
        meses_passados = []
        for m in range(1, today.month):  # only completed months
            meses_passados.append(f"{ano}-{m:02d}")

        if meses_passados:
            # Get set of (aluno, mes) that have boletos
            boleto_set = set()
            for _, row in df.iterrows():
                aid = row.get(id_aluno_col)
                mes = str(row.get("mes_competencia", ""))[:7]  # "YYYY-MM"
                if aid and mes:
                    boleto_set.add((aid, mes))

            for aluno_id in alunos_ativos_ids:
                for mes in meses_passados:
                    if (aluno_id, mes) not in boleto_set:
                        results.append({
                            "id_aluno": aluno_id,
                            "nome_aluno": _get_name(aluno_id),
                            "tipo": "MES_SEM_BOLETO",
                            "descricao": f"Sem boleto para competencia {mes}",
                            "valor_impacto": 0,
                        })

    # ── Rule 3: SEM_MENSALIDADE ──────────────────────────────────
    if id_aluno_col and servico_col:
        # Find students that have at least one "Mens%" service
        mask_mens = df[servico_col].astype(str).str.lower().str.startswith("mens")
        alunos_com_mens = set(df.loc[mask_mens, id_aluno_col].dropna().unique())

        for aluno_id in alunos_ativos_ids:
            if aluno_id not in alunos_com_mens:
                results.append({
                    "id_aluno": aluno_id,
                    "nome_aluno": _get_name(aluno_id),
                    "tipo": "SEM_MENSALIDADE",
                    "descricao": "Aluno ativo sem servico de mensalidade (Mens%)",
                    "valor_impacto": 0,
                })

    result_df = pd.DataFrame(results)
    return result_df


# ═══════════════════════════════════════════════════════════════════
# Adverse operations detection
# ═══════════════════════════════════════════════════════════════════

def detect_adverse_operations(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """Detect adverse financial operations (best-effort via API fields).

    Returns:
        (DataFrame of detected operations, list of warnings about missing fields)
    """
    results: List[Dict] = []
    warnings: List[str] = []

    if df.empty:
        return pd.DataFrame(results), ["Dataset vazio -- nenhuma analise possivel."]

    status_col = _find_column(df, [
        "situacao_titulo", "status", "situacao", "status_titulo",
    ])
    id_aluno_col = _find_column(df, ["_id_aluno_fetch", "id_aluno", "aluno_id"])
    nome_col = _find_column(df, ["nome_aluno", "aluno", "nome"])
    valor_col = _find_column(df, [
        "valor_documento", "valor", "valor_nominal", "valor_titulo", "vlr_nominal",
    ])
    data_op_col = _find_column(df, [
        "dt_processamento", "data_operacao", "dt_operacao", "data_registro",
        "data_alteracao", "dt_alteracao", "updated_at",
    ])
    data_pag_col = _find_column(df, [
        "dt_pagamento", "data_pagamento", "data_liquidacao",
    ])

    # ── 1. CANCELADO ─────────────────────────────────────────────
    if status_col:
        status_lower = df[status_col].astype(str).str.lower().str.strip()

        mask_cancel = status_lower.isin(["can", "cancelado", "cancelada", "cancel"])
        for _, row in df[mask_cancel].iterrows():
            results.append(_adverse_row(row, "CANCELADO", id_aluno_col, nome_col, valor_col))

        # ── 2. ESTORNADO ─────────────────────────────────────────
        mask_estorno = status_lower.isin(["est", "estornado", "estornada", "estorno"])
        for _, row in df[mask_estorno].iterrows():
            results.append(_adverse_row(row, "ESTORNADO", id_aluno_col, nome_col, valor_col))
    else:
        warnings.append(
            "Campo de status nao encontrado no dataset. "
            "Deteccao de cancelados/estornados nao e possivel."
        )

    # ── 3. BAIXA_RETROATIVA ──────────────────────────────────────
    if data_op_col and data_pag_col:
        dt_op = pd.to_datetime(df[data_op_col], errors="coerce")
        dt_pag = pd.to_datetime(df[data_pag_col], errors="coerce")
        both_valid = dt_op.notna() & dt_pag.notna()
        diff_days = (dt_op - dt_pag).dt.days
        mask_retro = both_valid & (diff_days > 7)

        for _, row in df[mask_retro].iterrows():
            days = int(diff_days[row.name])
            r = _adverse_row(row, "BAIXA_RETROATIVA", id_aluno_col, nome_col, valor_col)
            r["descricao"] = f"Liquidacao registrada {days} dias apos pagamento"
            results.append(r)
    else:
        missing = []
        if not data_op_col:
            missing.append("data de operacao/registro")
        if not data_pag_col:
            missing.append("data de pagamento")
        if missing:
            warnings.append(
                f"Campo(s) {', '.join(missing)} nao encontrado(s). "
                "Deteccao de baixas retroativas nao e possivel via API."
            )

    result_df = pd.DataFrame(results)
    return result_df, warnings


# ═══════════════════════════════════════════════════════════════════
# Export helpers
# ═══════════════════════════════════════════════════════════════════

def build_export_package(
    financial_df: pd.DataFrame,
    inconsistencies_df: pd.DataFrame,
    adverse_df: pd.DataFrame,
    mes_filter: Optional[str] = None,
) -> Dict[str, pd.DataFrame]:
    """Build multi-tab Excel export package.

    Returns dict of {sheet_name: DataFrame} for export_utils.df_to_excel_bytes().
    """
    sheets: Dict[str, pd.DataFrame] = {}

    # Filter by month if specified
    if mes_filter and "mes_competencia" in financial_df.columns:
        filtered = financial_df[financial_df["mes_competencia"] == mes_filter]
    else:
        filtered = financial_df

    # 1. Resumo Executivo
    resumo = _build_executive_summary(filtered)
    sheets["Resumo Executivo"] = resumo

    # 2. Aging
    if "aging_bucket" in filtered.columns:
        valor_col = _find_column(filtered, [
            "valor_documento", "valor", "valor_nominal", "valor_titulo",
        ])
        if valor_col:
            aging = filtered.groupby("aging_bucket", observed=True).agg(
                quantidade=("aging_bucket", "count"),
                **{"valor_total": (valor_col, lambda x: pd.to_numeric(x, errors="coerce").sum())},
            ).reset_index()
            aging.columns = ["Faixa", "Quantidade", "Valor Total (R$)"]
        else:
            aging = filtered["aging_bucket"].value_counts().reset_index()
            aging.columns = ["Faixa", "Quantidade"]
        sheets["Aging"] = aging

    # 3. Inadimplentes
    if "dias_atraso" in filtered.columns:
        inadimplentes = filtered[filtered["dias_atraso"] > 0].sort_values("dias_atraso", ascending=False)
        sheets["Inadimplentes"] = inadimplentes

    # 4. Inconsistencias
    if not inconsistencies_df.empty:
        sheets["Inconsistencias"] = inconsistencies_df

    # 5. Operacoes Adversas
    if not adverse_df.empty:
        sheets["Operacoes Adversas"] = adverse_df

    # 6. Base Detalhada
    sheets["Base Detalhada"] = filtered

    return sheets


# ═══════════════════════════════════════════════════════════════════
# KPI helpers
# ═══════════════════════════════════════════════════════════════════

def compute_kpis(df: pd.DataFrame) -> Dict[str, Any]:
    """Compute executive KPIs from the financial dataset."""
    kpis: Dict[str, Any] = {
        "receita_prevista": 0.0,
        "receita_recebida": 0.0,
        "inadimplencia_valor": 0.0,
        "inadimplencia_pct": 0.0,
        "total_titulos": len(df),
    }

    if df.empty:
        return kpis

    valor_col = _find_column(df, [
        "valor_documento", "valor", "valor_nominal", "valor_titulo", "vlr_nominal",
    ])
    valor_pago_col = _find_column(df, [
        "valor_recebido_total", "valor_pago", "vlr_pago", "valor_recebido",
    ])

    if valor_col:
        vn = pd.to_numeric(df[valor_col], errors="coerce")
        kpis["receita_prevista"] = float(vn.sum())

    if valor_pago_col:
        vp = pd.to_numeric(df[valor_pago_col], errors="coerce")
        kpis["receita_recebida"] = float(vp.sum())

    kpis["inadimplencia_valor"] = kpis["receita_prevista"] - kpis["receita_recebida"]

    if kpis["receita_prevista"] > 0:
        kpis["inadimplencia_pct"] = (kpis["inadimplencia_valor"] / kpis["receita_prevista"]) * 100
    else:
        kpis["inadimplencia_pct"] = 0.0

    return kpis


def top_servicos(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Top N services by revenue."""
    servico_col = _find_column(df, [
        "nome_servico", "servico", "descricao_servico",
    ])
    valor_col = _find_column(df, [
        "valor_documento", "valor", "valor_nominal", "valor_titulo", "vlr_nominal",
    ])

    if not servico_col or not valor_col:
        return pd.DataFrame()

    df_copy = df.copy()
    df_copy["_valor_num"] = pd.to_numeric(df_copy[valor_col], errors="coerce")
    result = (
        df_copy.groupby(servico_col, dropna=False)["_valor_num"]
        .sum()
        .sort_values(ascending=False)
        .head(n)
        .reset_index()
    )
    result.columns = ["Servico", "Receita Total (R$)"]
    return result


def mix_forma_recebimento(df: pd.DataFrame) -> pd.DataFrame:
    """Revenue mix by payment method."""
    forma_col = _find_column(df, [
        "forma_recebimento", "forma_pagamento", "tipo_recebimento",
    ])
    valor_col = _find_column(df, [
        "valor_documento", "valor", "valor_nominal", "valor_titulo", "vlr_nominal",
    ])

    if not forma_col or not valor_col:
        return pd.DataFrame()

    df_copy = df.copy()
    df_copy["_valor_num"] = pd.to_numeric(df_copy[valor_col], errors="coerce")
    result = (
        df_copy.groupby(forma_col, dropna=False)["_valor_num"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    total = result.iloc[:, 1].sum()
    result["% do Total"] = (result.iloc[:, 1] / total * 100).round(1) if total > 0 else 0
    result.columns = ["Forma de Recebimento", "Valor Total (R$)", "% do Total"]
    return result


# ═══════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════

def _find_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """Return the first column name that exists in df, or None."""
    cols_lower = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in cols_lower:
            return cols_lower[c.lower()]
    return None


def _adverse_row(
    row: pd.Series,
    tipo: str,
    id_aluno_col: Optional[str],
    nome_col: Optional[str],
    valor_col: Optional[str],
) -> Dict:
    return {
        "id_aluno": row.get(id_aluno_col, "") if id_aluno_col else "",
        "nome_aluno": row.get(nome_col, "") if nome_col else "",
        "tipo": tipo,
        "descricao": f"Titulo {tipo.lower()}",
        "valor_impacto": float(pd.to_numeric(row.get(valor_col, 0), errors="coerce") or 0) if valor_col else 0,
    }


def _build_executive_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Build a summary DataFrame for the executive tab."""
    kpis = compute_kpis(df)
    summary = pd.DataFrame([
        {"Indicador": "Receita Prevista", "Valor": f"R$ {kpis['receita_prevista']:,.2f}"},
        {"Indicador": "Receita Recebida", "Valor": f"R$ {kpis['receita_recebida']:,.2f}"},
        {"Indicador": "Inadimplencia (R$)", "Valor": f"R$ {kpis['inadimplencia_valor']:,.2f}"},
        {"Indicador": "Inadimplencia (%)", "Valor": f"{kpis['inadimplencia_pct']:.1f}%"},
        {"Indicador": "Total de Titulos", "Valor": str(kpis['total_titulos'])},
    ])
    return summary
