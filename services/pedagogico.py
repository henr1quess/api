"""Pedagogical analytics: risk detection, diary audit, grade consolidation.

Provides:
- Bulk fetch of student frequency and report cards (with progress tracking)
- Bulk fetch of diary frequency data (turma-based)
- Risk detection (truancy + low grades)
- Diary audit (missing entries / compliance)
"""

import time
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from services.cache_store import CacheStore, TTL_PERMANENT, DatasetMeta
from services.frequency import _classify_presence

# ═══════════════════════════════════════════════════════════════════
# Bulk fetch functions
# ═══════════════════════════════════════════════════════════════════

_FETCH_DELAY = 0.15  # seconds between API calls


def fetch_all_frequencia_aluno(
    client: Any,
    store: CacheStore,
    alunos_ids: List[int],
    data_inicial: str = "2026-01-01",
    force_refresh: bool = False,
) -> Tuple[pd.DataFrame, Optional[DatasetMeta]]:
    """Fetch frequency records for every student and return consolidated DataFrame.

    Uses listar_frequencia_aluno (per-student endpoint).
    Permanent cache — only calls API on first load or manual refresh.
    """
    from activesoft_client.endpoints import listar_frequencia_aluno

    cache_key = store.make_key(
        client.base_url,
        "pedagogico/frequencia_consolidada",
        {"data_inicial": data_inicial, "total_alunos": str(len(alunos_ids))},
        client._session.headers.get("Authorization", ""),
    )

    if not force_refresh:
        cached = store._load(cache_key)
        if cached is not None:
            return cached[0], cached[1]

    all_records: List[Dict] = []
    progress = st.progress(0, text="Carregando frequencia...")
    errors: List[str] = []

    today_str = date.today().isoformat()

    for i, aluno_id in enumerate(alunos_ids):
        try:
            records = listar_frequencia_aluno(
                client,
                aluno_id=aluno_id,
                data_inicial=data_inicial,
                data_final=today_str,
            )
            if isinstance(records, list):
                for r in records:
                    r["_id_aluno_fetch"] = aluno_id
                all_records.extend(records)
        except Exception as e:
            errors.append(f"Aluno {aluno_id}: {e}")

        progress.progress(
            (i + 1) / len(alunos_ids),
            text=f"Carregando frequencia: {i + 1}/{len(alunos_ids)}",
        )

        if i < len(alunos_ids) - 1:
            time.sleep(_FETCH_DELAY)

    progress.empty()

    if errors:
        st.warning(f"{len(errors)} erro(s) ao buscar frequencia. Primeiros 5:")
        for err in errors[:5]:
            st.caption(f"  - {err}")

    df = pd.DataFrame(all_records) if all_records else pd.DataFrame()
    meta = store._save(
        cache_key, "pedagogico/frequencia_consolidada",
        {"data_inicial": data_inicial}, df, TTL_PERMANENT,
    )
    return df, meta


def fetch_all_boletins(
    client: Any,
    store: CacheStore,
    alunos_ids: List[int],
    force_refresh: bool = False,
) -> Tuple[pd.DataFrame, Optional[DatasetMeta]]:
    """Fetch report cards for every student and return consolidated DataFrame.

    Uses detalhe_boletim (per-student, returns dict — needs flatten).
    Permanent cache.
    """
    from activesoft_client.endpoints import detalhe_boletim

    cache_key = store.make_key(
        client.base_url,
        "pedagogico/boletins_consolidados",
        {"total_alunos": str(len(alunos_ids))},
        client._session.headers.get("Authorization", ""),
    )

    if not force_refresh:
        cached = store._load(cache_key)
        if cached is not None:
            return cached[0], cached[1]

    all_records: List[Dict] = []
    progress = st.progress(0, text="Carregando boletins...")
    errors: List[str] = []

    for i, aluno_id in enumerate(alunos_ids):
        try:
            result = detalhe_boletim(client, aluno_id=aluno_id, turmas_ativas=True)
            flattened = _flatten_boletim(aluno_id, result)
            all_records.extend(flattened)
        except Exception as e:
            errors.append(f"Aluno {aluno_id}: {e}")

        progress.progress(
            (i + 1) / len(alunos_ids),
            text=f"Carregando boletins: {i + 1}/{len(alunos_ids)}",
        )

        if i < len(alunos_ids) - 1:
            time.sleep(_FETCH_DELAY)

    progress.empty()

    if errors:
        st.warning(f"{len(errors)} erro(s) ao buscar boletins. Primeiros 5:")
        for err in errors[:5]:
            st.caption(f"  - {err}")

    df = pd.DataFrame(all_records) if all_records else pd.DataFrame()
    meta = store._save(
        cache_key, "pedagogico/boletins_consolidados",
        {}, df, TTL_PERMANENT,
    )
    return df, meta


def fetch_diarios_completos(
    client: Any,
    store: CacheStore,
    turmas_ids: List[int],
    force_refresh: bool = False,
) -> Tuple[pd.DataFrame, Optional[DatasetMeta]]:
    """Fetch all diarios and their frequency data (turma-based approach).

    For each turma: fetch diarios, then for each diario: fetch diario_frequencia.
    Returns consolidated DataFrame with frequency classification.
    """
    from activesoft_client.endpoints import diarios, diario_frequencia

    cache_key = store.make_key(
        client.base_url,
        "pedagogico/diarios_completos",
        {"total_turmas": str(len(turmas_ids))},
        client._session.headers.get("Authorization", ""),
    )

    if not force_refresh:
        cached = store._load(cache_key)
        if cached is not None:
            return cached[0], cached[1]

    all_records: List[Dict] = []
    errors: List[str] = []

    # Phase 1: fetch diarios per turma
    progress = st.progress(0, text="Carregando diarios...")
    diarios_map: Dict[int, List[Dict]] = {}  # turma_id -> list of diarios

    for i, turma_id in enumerate(turmas_ids):
        try:
            turma_diarios = diarios(client, turma_id=turma_id)
            diarios_map[turma_id] = turma_diarios if isinstance(turma_diarios, list) else []
        except Exception as e:
            errors.append(f"Turma {turma_id}: {e}")
            diarios_map[turma_id] = []

        progress.progress(
            (i + 1) / len(turmas_ids),
            text=f"Carregando diarios: {i + 1}/{len(turmas_ids)} turmas",
        )
        if i < len(turmas_ids) - 1:
            time.sleep(_FETCH_DELAY)

    # Phase 2: fetch frequency per diario
    all_diario_ids = []
    for turma_id, d_list in diarios_map.items():
        for d in d_list:
            did = d.get("id")
            if did is not None:
                all_diario_ids.append((turma_id, d))

    if all_diario_ids:
        progress.progress(0, text="Carregando frequencia dos diarios...")

    for i, (turma_id, diario_info) in enumerate(all_diario_ids):
        did = diario_info.get("id")
        try:
            freq_data = diario_frequencia(client, diario_id=did)
            if isinstance(freq_data, list):
                # Process each student row
                freq_df = pd.DataFrame(freq_data) if freq_data else pd.DataFrame()
                if not freq_df.empty:
                    freq_cols = [c for c in freq_df.columns if c.startswith("presenca_falta_")]
                    summary = _summarize_diario_freq(freq_df, freq_cols)
                    for rec in summary:
                        rec["turma_id"] = turma_id
                        rec["diario_id"] = did
                        rec["disciplina"] = diario_info.get("nome_disciplina", "")
                        rec["fase_nota"] = diario_info.get("nome_fase", "")
                    all_records.extend(summary)
        except Exception as e:
            errors.append(f"Diario {did}: {e}")

        if all_diario_ids:
            progress.progress(
                (i + 1) / len(all_diario_ids),
                text=f"Carregando frequencia: {i + 1}/{len(all_diario_ids)} diarios",
            )
        if i < len(all_diario_ids) - 1:
            time.sleep(_FETCH_DELAY)

    progress.empty()

    if errors:
        st.warning(f"{len(errors)} erro(s) ao buscar diarios/frequencia. Primeiros 5:")
        for err in errors[:5]:
            st.caption(f"  - {err}")

    df = pd.DataFrame(all_records) if all_records else pd.DataFrame()
    meta = store._save(
        cache_key, "pedagogico/diarios_completos",
        {}, df, TTL_PERMANENT,
    )
    return df, meta


# ═══════════════════════════════════════════════════════════════════
# Risk detection — Farol de Risco
# ═══════════════════════════════════════════════════════════════════

def detect_risco_evasao(
    freq_df: pd.DataFrame,
    boletim_df: pd.DataFrame,
    threshold_faltas_pct: float = 25.0,
    threshold_nota_min: float = 6.0,
    min_disciplinas_risco: int = 3,
) -> pd.DataFrame:
    """Detect students at risk of dropout or failure.

    Rules:
    1. FALTAS_EXCESSIVAS: >threshold_faltas_pct% absence in current month
    2. NOTAS_CRITICAS: avg grade < threshold_nota_min in 3+ subjects
    3. RISCO_COMBINADO: both conditions met (highest risk level)

    Returns: id_aluno, nome_aluno, turma, tipo_risco, nivel_risco, detalhes, acao_sugerida
    """
    results: List[Dict] = []

    # ── Frequency-based risk ─────────────────────────────────────
    alunos_freq_risco = set()
    if not freq_df.empty:
        freq_risk = _analyze_frequency_risk(freq_df, threshold_faltas_pct)
        for rec in freq_risk:
            alunos_freq_risco.add(rec["id_aluno"])
            results.append(rec)

    # ── Grade-based risk ─────────────────────────────────────────
    alunos_nota_risco = set()
    if not boletim_df.empty:
        grade_risk = _analyze_grade_risk(boletim_df, threshold_nota_min, min_disciplinas_risco)
        for rec in grade_risk:
            alunos_nota_risco.add(rec["id_aluno"])
            results.append(rec)

    # ── Combined risk ────────────────────────────────────────────
    combined = alunos_freq_risco & alunos_nota_risco
    for aid in combined:
        # Find existing entries and upgrade them
        for r in results:
            if r["id_aluno"] == aid:
                r["nivel_risco"] = "ALTO"

        results.append({
            "id_aluno": aid,
            "nome_aluno": "",
            "turma": "",
            "tipo_risco": "RISCO_COMBINADO",
            "nivel_risco": "ALTO",
            "detalhes": "Faltas excessivas + notas criticas",
            "acao_sugerida": "Convocar familia com urgencia",
        })

    result_df = pd.DataFrame(results)

    # Enrich nome_aluno from boletim_df or freq_df
    if not result_df.empty:
        nome_map = {}
        for src_df in [boletim_df, freq_df]:
            if src_df.empty:
                continue
            id_col = _find_col(src_df, ["id_aluno", "_id_aluno_fetch", "aluno_id"])
            nome_col = _find_col(src_df, ["nome_aluno", "nome", "nome_completo"])
            if id_col and nome_col:
                for _, row in src_df[[id_col, nome_col]].drop_duplicates().iterrows():
                    nome_map[row[id_col]] = row[nome_col]
        if nome_map:
            result_df["nome_aluno"] = result_df["id_aluno"].map(nome_map).fillna(result_df["nome_aluno"])

    return result_df


# ═══════════════════════════════════════════════════════════════════
# Diary audit — Auditoria de Diarios
# ═══════════════════════════════════════════════════════════════════

def audit_diarios_docentes(
    diarios_df: pd.DataFrame,
    dias_sem_registro_alerta: int = 7,
) -> pd.DataFrame:
    """Audit teacher compliance with diary entries.

    Rules:
    1. SEM_FREQUENCIA_SEMANA: diarios with no frequency entry in the current week
    2. ALTO_NAO_REGISTRADO: diarios where >50% of entries are 'Nao_registrado'

    Returns: turma_id, disciplina, fase_nota, diario_id, tipo_pendencia,
             total_registros, nao_registrado_pct, status
    """
    results: List[Dict] = []

    if diarios_df.empty:
        return pd.DataFrame(results)

    # Group by diario
    group_cols = []
    for col in ["diario_id", "turma_id", "disciplina", "fase_nota"]:
        if col in diarios_df.columns:
            group_cols.append(col)

    if not group_cols or "diario_id" not in diarios_df.columns:
        return pd.DataFrame(results)

    for diario_id, group in diarios_df.groupby("diario_id"):
        turma_id = group["turma_id"].iloc[0] if "turma_id" in group.columns else ""
        disciplina = group["disciplina"].iloc[0] if "disciplina" in group.columns else ""
        fase_nota = group["fase_nota"].iloc[0] if "fase_nota" in group.columns else ""

        total = len(group)
        nao_reg = 0
        presencas = 0
        faltas = 0

        for col in ["Presenca", "Falta", "Nao_registrado", "Dispensa", "Justificada"]:
            if col in group.columns:
                if col == "Nao_registrado":
                    nao_reg = int(group[col].sum())
                elif col == "Presenca":
                    presencas = int(group[col].sum())
                elif col == "Falta":
                    faltas = int(group[col].sum())

        total_aulas = 0
        if "Total_aulas" in group.columns:
            total_aulas = int(group["Total_aulas"].max())

        total_marks = presencas + faltas + nao_reg
        nao_reg_pct = (nao_reg / total_marks * 100) if total_marks > 0 else 0

        # Rule 1: High percentage of unregistered entries
        if nao_reg_pct > 50:
            results.append({
                "turma_id": turma_id,
                "disciplina": disciplina,
                "fase_nota": fase_nota,
                "diario_id": diario_id,
                "tipo_pendencia": "SEM_FREQUENCIA_SEMANA",
                "total_registros": total,
                "total_aulas": total_aulas,
                "nao_registrado_pct": round(nao_reg_pct, 1),
                "status": "Pendente",
            })
        elif nao_reg_pct > 20:
            results.append({
                "turma_id": turma_id,
                "disciplina": disciplina,
                "fase_nota": fase_nota,
                "diario_id": diario_id,
                "tipo_pendencia": "FREQUENCIA_PARCIAL",
                "total_registros": total,
                "total_aulas": total_aulas,
                "nao_registrado_pct": round(nao_reg_pct, 1),
                "status": "Atencao",
            })

    result_df = pd.DataFrame(results)
    if not result_df.empty:
        result_df = result_df.sort_values("nao_registrado_pct", ascending=False)
    return result_df


def compute_compliance_by_turma(audit_df: pd.DataFrame) -> pd.DataFrame:
    """Compute diary compliance percentage by turma."""
    if audit_df.empty or "turma_id" not in audit_df.columns:
        return pd.DataFrame()

    # compliance = diarios without issues / total diarios
    total = audit_df.groupby("turma_id").size().reset_index(name="total_diarios")
    pendentes = audit_df[audit_df["status"] == "Pendente"].groupby("turma_id").size().reset_index(name="pendentes")

    merged = total.merge(pendentes, on="turma_id", how="left")
    merged["pendentes"] = merged["pendentes"].fillna(0).astype(int)
    merged["compliance_pct"] = ((1 - merged["pendentes"] / merged["total_diarios"]) * 100).round(1)
    merged = merged.sort_values("compliance_pct")
    return merged


# ═══════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════

def _find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """Return the first column name that exists in df, or None."""
    cols_lower = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in cols_lower:
            return cols_lower[c.lower()]
    return None


def _flatten_boletim(aluno_id: int, data: Any) -> List[Dict]:
    """Flatten a detalhe_boletim response into tabular rows.

    The response structure varies — this handles common patterns:
    - dict with nested 'turmas' -> 'disciplinas' -> 'notas'
    - list of dicts with grade fields
    - single dict with flat fields
    """
    rows: List[Dict] = []

    if data is None:
        return rows

    if isinstance(data, dict):
        # Try nested pattern: {turmas: [{disciplinas: [{notas: [...]}]}]}
        turmas = data.get("turmas", data.get("turma", []))
        if isinstance(turmas, list):
            for turma in turmas:
                turma_nome = turma.get("nome_turma", turma.get("nome", ""))
                turma_id = turma.get("id_turma", turma.get("id", ""))
                disciplinas = turma.get("disciplinas", turma.get("materias", []))
                if isinstance(disciplinas, list):
                    for disc in disciplinas:
                        row = {
                            "id_aluno": aluno_id,
                            "turma_id": turma_id,
                            "turma_nome": turma_nome,
                            "disciplina": disc.get("nome_disciplina", disc.get("nome", "")),
                            "disciplina_id": disc.get("id_disciplina", disc.get("id", "")),
                        }
                        # Extract grade fields (fase1, fase2, media, etc.)
                        notas = disc.get("notas", disc.get("fases", {}))
                        if isinstance(notas, dict):
                            row.update(notas)
                        elif isinstance(notas, list):
                            for n in notas:
                                if isinstance(n, dict):
                                    fase = n.get("fase", n.get("nome_fase", ""))
                                    nota = n.get("nota", n.get("valor", ""))
                                    if fase:
                                        row[f"nota_{fase}"] = nota
                        # Also check flat grade fields
                        for k, v in disc.items():
                            if k.startswith("nota") or k.startswith("media") or k.startswith("fase"):
                                row[k] = v
                        rows.append(row)
                    if not disciplinas:
                        # No disciplines, just record that aluno has this turma
                        rows.append({
                            "id_aluno": aluno_id,
                            "turma_id": turma_id,
                            "turma_nome": turma_nome,
                        })
            if not turmas:
                # Flat structure — just record all fields
                row = {"id_aluno": aluno_id}
                row.update({k: v for k, v in data.items() if not isinstance(v, (list, dict))})
                rows.append(row)
        elif isinstance(turmas, dict):
            # Single turma as dict
            row = {"id_aluno": aluno_id}
            row.update({k: v for k, v in turmas.items() if not isinstance(v, (list, dict))})
            rows.append(row)
        else:
            # Flat dict — just record all scalar fields
            row = {"id_aluno": aluno_id}
            row.update({k: v for k, v in data.items() if not isinstance(v, (list, dict))})
            rows.append(row)

    elif isinstance(data, list):
        for item in data:
            row = {"id_aluno": aluno_id}
            if isinstance(item, dict):
                row.update({k: v for k, v in item.items() if not isinstance(v, (list, dict))})
            rows.append(row)

    return rows if rows else [{"id_aluno": aluno_id}]


def _analyze_frequency_risk(
    freq_df: pd.DataFrame,
    threshold_pct: float,
) -> List[Dict]:
    """Analyze frequency data for excessive absences."""
    results: List[Dict] = []

    id_col = _find_col(freq_df, ["id_aluno", "_id_aluno_fetch", "aluno_id"])
    if not id_col:
        return results

    # Try to group by student and compute absence rate
    # The freq data from listar_frequencia_aluno has varied structure
    # Look for date/tipo fields
    tipo_col = _find_col(freq_df, ["tipo_marcacao", "tipo", "presenca"])
    data_col = _find_col(freq_df, ["data", "data_aula", "data_registro"])

    if tipo_col:
        # Count total entries and absences per student
        for aluno_id, group in freq_df.groupby(id_col):
            total = len(group)
            if total == 0:
                continue
            falta_terms = ["f", "falta", "ausente", "ausencia"]
            faltas = group[tipo_col].astype(str).str.lower().str.strip().isin(falta_terms).sum()
            pct = (faltas / total) * 100

            if pct >= threshold_pct:
                nivel = "ALTO" if pct >= threshold_pct * 1.5 else "MEDIO"
                results.append({
                    "id_aluno": aluno_id,
                    "nome_aluno": "",
                    "turma": "",
                    "tipo_risco": "FALTAS_EXCESSIVAS",
                    "nivel_risco": nivel,
                    "detalhes": f"{pct:.1f}% de faltas ({int(faltas)}/{total})",
                    "acao_sugerida": "Acompanhamento pedagogico" if nivel == "MEDIO" else "Convocar familia",
                })
    else:
        # Alternative: look for presenca_falta_* columns (diario format)
        freq_cols = [c for c in freq_df.columns if c.startswith("presenca_falta_")]
        if freq_cols:
            for aluno_id, group in freq_df.groupby(id_col):
                total = 0
                faltas = 0
                for _, row in group.iterrows():
                    for col in freq_cols:
                        cls = _classify_presence(row.get(col))
                        if cls != "Nao_registrado":
                            total += 1
                        if cls == "Falta":
                            faltas += 1
                if total == 0:
                    continue
                pct = (faltas / total) * 100
                if pct >= threshold_pct:
                    nivel = "ALTO" if pct >= threshold_pct * 1.5 else "MEDIO"
                    results.append({
                        "id_aluno": aluno_id,
                        "nome_aluno": "",
                        "turma": "",
                        "tipo_risco": "FALTAS_EXCESSIVAS",
                        "nivel_risco": nivel,
                        "detalhes": f"{pct:.1f}% de faltas ({faltas}/{total})",
                        "acao_sugerida": "Acompanhamento pedagogico" if nivel == "MEDIO" else "Convocar familia",
                    })

    return results


def _analyze_grade_risk(
    boletim_df: pd.DataFrame,
    threshold_nota: float,
    min_disciplinas: int,
) -> List[Dict]:
    """Analyze grade data for students with critical grades."""
    results: List[Dict] = []

    if boletim_df.empty or "id_aluno" not in boletim_df.columns:
        return results

    # Find grade columns
    nota_cols = [c for c in boletim_df.columns if c.startswith("nota") or c.startswith("media")]

    if not nota_cols:
        # Try to find any numeric-looking columns that might be grades
        for c in boletim_df.columns:
            if c.lower() in ("nota", "media", "media_final", "nota_final"):
                nota_cols.append(c)

    if not nota_cols:
        return results

    for aluno_id, group in boletim_df.groupby("id_aluno"):
        disciplinas_baixas = []
        for _, row in group.iterrows():
            disc = row.get("disciplina", "Desconhecida")
            for nc in nota_cols:
                val = pd.to_numeric(row.get(nc), errors="coerce")
                if pd.notna(val) and val < threshold_nota:
                    disciplinas_baixas.append(f"{disc} ({nc}={val:.1f})")
                    break  # one low grade per discipline is enough

        if len(disciplinas_baixas) >= min_disciplinas:
            nivel = "ALTO" if len(disciplinas_baixas) >= min_disciplinas + 2 else "MEDIO"
            turma = group["turma_nome"].iloc[0] if "turma_nome" in group.columns else ""
            results.append({
                "id_aluno": aluno_id,
                "nome_aluno": "",
                "turma": turma,
                "tipo_risco": "NOTAS_CRITICAS",
                "nivel_risco": nivel,
                "detalhes": f"{len(disciplinas_baixas)} disciplinas abaixo de {threshold_nota}: {', '.join(disciplinas_baixas[:5])}",
                "acao_sugerida": "Acompanhamento pedagogico" if nivel == "MEDIO" else "Convocar familia",
            })

    return results


def _summarize_diario_freq(
    freq_df: pd.DataFrame,
    freq_cols: List[str],
) -> List[Dict]:
    """Summarize frequency data for a single diario."""
    rows: List[Dict] = []
    id_cols = [c for c in freq_df.columns if not c.startswith("presenca_falta_")]

    for _, row in freq_df.iterrows():
        counts = {
            "Presenca": 0,
            "Falta": 0,
            "Dispensa": 0,
            "Justificada": 0,
            "Nao_registrado": 0,
        }
        for col in freq_cols:
            cls = _classify_presence(row.get(col))
            counts[cls] += 1

        entry: Dict[str, Any] = {c: row[c] for c in id_cols if c in row.index}
        entry.update(counts)
        entry["Total_aulas"] = len(freq_cols)
        rows.append(entry)

    return rows
