"""Grade import service – CSV parsing, validation, payload building."""

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from activesoft_client import ActiveSoftClient
from activesoft_client import endpoints as ep
from services.validators import (
    NOTA_COLUMNS,
    CorrecaoProva,
    CorrecaoProvaNota,
    normalize_nota,
)


def parse_notas_csv(file_bytes: bytes, sep: str = ";") -> pd.DataFrame:
    """Read an uploaded CSV of grades into a DataFrame.

    Expected columns: matricula + any of nota01..nota10.
    """
    df = pd.read_csv(
        pd.io.common.BytesIO(file_bytes),
        sep=sep,
        dtype=str,
        encoding="utf-8-sig",
    )
    df.columns = [c.strip().lower() for c in df.columns]
    if "matricula" not in df.columns:
        raise ValueError("CSV precisa ter coluna 'matricula'.")
    return df


def validate_grades(
    df: pd.DataFrame,
    client: ActiveSoftClient,
    turma_id: int,
    disciplina_id: int,
    fase_nota_id: int,
) -> pd.DataFrame:
    """Validate each row and return df with a 'status' and 'msg' column."""
    # Fetch known matriculas
    try:
        alunos = ep.acesso_alunos(client)
        known_matriculas = {str(a.get("matricula", "")).strip() for a in alunos}
    except Exception:
        known_matriculas = set()

    statuses: List[str] = []
    msgs: List[str] = []

    nota_cols = [c for c in df.columns if c in NOTA_COLUMNS]
    if not nota_cols:
        raise ValueError(
            "CSV precisa ter ao menos uma coluna de nota (nota01..nota10)."
        )

    for _, row in df.iterrows():
        row_msgs: List[str] = []
        matricula = str(row.get("matricula", "")).strip()

        if not matricula:
            statuses.append("ERRO")
            msgs.append("Matricula vazia")
            continue

        if known_matriculas and matricula not in known_matriculas:
            row_msgs.append(f"Matricula '{matricula}' nao encontrada no sistema")

        has_nota = False
        for col in nota_cols:
            raw = str(row.get(col, "")).strip()
            if raw and raw.lower() not in ("nan", "none", ""):
                normalized = normalize_nota(raw)
                if normalized is None:
                    row_msgs.append(f"{col}: valor invalido '{raw}'")
                else:
                    has_nota = True

        if not has_nota and not row_msgs:
            row_msgs.append("Nenhuma nota preenchida")

        if any("ERRO" in m or "invalido" in m or "nao encontrada" in m for m in row_msgs):
            statuses.append("ERRO")
        elif row_msgs:
            statuses.append("WARN")
        else:
            statuses.append("OK")
        msgs.append("; ".join(row_msgs) if row_msgs else "")

    result = df.copy()
    result["_status"] = statuses
    result["_msg"] = msgs
    return result


def build_payloads(
    df: pd.DataFrame,
    turma_id: int,
    disciplina_id: int,
    fase_nota_id: int,
    sobrescrever_nota: bool = False,
    sobrescrever_nota_confirmada: bool = False,
    batch_size: int = 200,
) -> List[Dict]:
    """Build list of CorrecaoProva payloads (chunked by batch_size).

    Only rows with _status == 'OK' are included.
    """
    ok_rows = df[df["_status"] == "OK"] if "_status" in df.columns else df
    nota_cols = [c for c in df.columns if c in NOTA_COLUMNS]

    all_notas: List[Dict] = []
    for _, row in ok_rows.iterrows():
        nota_dict: Dict[str, Any] = {"matricula": str(row["matricula"]).strip()}
        for col in nota_cols:
            val = normalize_nota(str(row.get(col, "")))
            if val is not None:
                nota_dict[col] = val
        all_notas.append(nota_dict)

    # Chunk
    payloads: List[Dict] = []
    for i in range(0, len(all_notas), batch_size):
        chunk = all_notas[i : i + batch_size]
        payloads.append(
            ep.build_correcao_prova(
                turma_id=turma_id,
                fase_nota_id=fase_nota_id,
                disciplina_id=disciplina_id,
                notas=chunk,
                sobrescrever_nota=sobrescrever_nota,
                sobrescrever_nota_confirmada=sobrescrever_nota_confirmada,
            )
        )
    return payloads
