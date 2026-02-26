"""Frequency services – query attendance data and build marking payloads."""

from typing import Any, Dict, List, Optional

import pandas as pd

from activesoft_client import ActiveSoftClient
from activesoft_client import endpoints as ep
from services.validators import MarcacaoFrequencia


# ═══════════════════════════════════════════════════════════════════
# Consulta de frequencia (GET)
# ═══════════════════════════════════════════════════════════════════

PRESENCE_CODES = {
    "\u2022": "Presenca",     # bullet "•"
    "F": "Falta",
    "D": "Dispensa",
    "J": "Justificada",
}


def fetch_frequencia_raw(client: ActiveSoftClient, diario_id: int) -> pd.DataFrame:
    """Fetch raw attendance data for a diario and return as DataFrame."""
    data = ep.diario_frequencia(client, diario_id)
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)


def summarize_frequencia(df: pd.DataFrame) -> pd.DataFrame:
    """From raw frequency DataFrame, produce a summary per student.

    Counts columns matching 'presenca_falta_*' using the presence codes.
    """
    if df.empty:
        return df

    freq_cols = [c for c in df.columns if c.startswith("presenca_falta_")]
    if not freq_cols:
        return df

    # Identify student columns (everything except presenca_falta_*)
    id_cols = [c for c in df.columns if not c.startswith("presenca_falta_")]

    summary_rows: List[Dict] = []
    for _, row in df.iterrows():
        counts = {"Presenca": 0, "Falta": 0, "Dispensa": 0, "Justificada": 0, "Nao_registrado": 0}
        for col in freq_cols:
            val = row.get(col)
            if val is None or (isinstance(val, float) and pd.isna(val)):
                counts["Nao_registrado"] += 1
            elif str(val).strip() in PRESENCE_CODES:
                counts[PRESENCE_CODES[str(val).strip()]] += 1
            else:
                counts["Nao_registrado"] += 1

        entry: Dict[str, Any] = {}
        for c in id_cols:
            entry[c] = row[c]
        entry.update(counts)
        entry["Total_aulas"] = len(freq_cols)
        summary_rows.append(entry)

    return pd.DataFrame(summary_rows)


# ═══════════════════════════════════════════════════════════════════
# Marcacao de frequencia (POST simulation)
# ═══════════════════════════════════════════════════════════════════

def parse_marcacao_csv(file_bytes: bytes, sep: str = ";") -> pd.DataFrame:
    """Parse uploaded CSV for frequency marking."""
    df = pd.read_csv(
        pd.io.common.BytesIO(file_bytes),
        sep=sep,
        dtype=str,
        encoding="utf-8-sig",
    )
    df.columns = [c.strip().lower() for c in df.columns]
    required = {"data_hora", "tipo_entrada_saida", "matricula"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Colunas obrigatorias ausentes: {missing}")
    return df


def validate_marcacoes(df: pd.DataFrame) -> pd.DataFrame:
    """Validate each row and add _status / _msg columns."""
    statuses: List[str] = []
    msgs: List[str] = []

    for _, row in df.iterrows():
        row_msgs: List[str] = []

        matricula = str(row.get("matricula", "")).strip()
        if not matricula or matricula.lower() in ("nan", "none"):
            row_msgs.append("Matricula vazia")

        tipo = str(row.get("tipo_entrada_saida", "")).strip().upper()
        if tipo not in ("E", "S"):
            row_msgs.append(f"tipo_entrada_saida invalido: '{tipo}' (deve ser E ou S)")

        data_hora = str(row.get("data_hora", "")).strip()
        if not data_hora or data_hora.lower() in ("nan", "none"):
            row_msgs.append("data_hora vazia")

        comentario = str(row.get("comentario", "")).strip()
        if comentario and comentario.lower() not in ("nan", "none", "") and len(comentario) > 50:
            row_msgs.append(f"comentario excede 50 caracteres ({len(comentario)})")

        if row_msgs:
            statuses.append("ERRO")
        else:
            statuses.append("OK")
        msgs.append("; ".join(row_msgs) if row_msgs else "")

    result = df.copy()
    result["_status"] = statuses
    result["_msg"] = msgs
    return result


def build_marcacao_payloads(df: pd.DataFrame) -> List[Dict]:
    """Build list of MarcacaoFrequencia payloads from validated rows."""
    ok_rows = df[df["_status"] == "OK"] if "_status" in df.columns else df
    payloads: List[Dict] = []
    for _, row in ok_rows.iterrows():
        comentario = str(row.get("comentario", "")).strip()
        if comentario.lower() in ("nan", "none", ""):
            comentario = None

        id_resp_raw = str(row.get("id_responsavel_acompanhante", "")).strip()
        id_resp = None
        if id_resp_raw and id_resp_raw.lower() not in ("nan", "none", ""):
            try:
                id_resp = int(float(id_resp_raw))
            except ValueError:
                pass

        payloads.append(
            ep.build_marcacao_frequencia(
                data_hora=str(row["data_hora"]).strip(),
                tipo=str(row["tipo_entrada_saida"]).strip().upper(),
                matricula=str(row["matricula"]).strip(),
                id_responsavel=id_resp,
                comentario=comentario,
            )
        )
    return payloads
