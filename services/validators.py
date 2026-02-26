"""Pydantic models and validation helpers for SigaWeb payloads."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ═══════════════════════════════════════════════════════════════════
# CorrecaoProva (grade correction)
# ═══════════════════════════════════════════════════════════════════

class CorrecaoProvaNota(BaseModel):
    matricula: str = Field(..., min_length=1, max_length=50)
    nota01: Optional[str] = None
    nota02: Optional[str] = None
    nota03: Optional[str] = None
    nota04: Optional[str] = None
    nota05: Optional[str] = None
    nota06: Optional[str] = None
    nota07: Optional[str] = None
    nota08: Optional[str] = None
    nota09: Optional[str] = None
    nota10: Optional[str] = None


class CorrecaoProva(BaseModel):
    turma_id: int
    fase_nota_id: int
    disciplina_id: int
    sobrescrever_nota: bool = False
    sobrescrever_nota_confirmada: bool = False
    notas: List[CorrecaoProvaNota] = Field(..., min_length=1)


# ═══════════════════════════════════════════════════════════════════
# MarcacaoFrequencia (attendance marking)
# ═══════════════════════════════════════════════════════════════════

class MarcacaoFrequencia(BaseModel):
    data_hora: str
    tipo_entrada_saida: Literal["E", "S"]
    matricula: str = Field(..., min_length=1, max_length=50)
    id_responsavel_acompanhante: Optional[int] = None
    comentario: Optional[str] = Field(None, max_length=50)

    @field_validator("tipo_entrada_saida", mode="before")
    @classmethod
    def uppercase_tipo(cls, v: str) -> str:
        return v.strip().upper() if isinstance(v, str) else v


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def normalize_nota(raw: str) -> Optional[str]:
    """Normalize a grade string: '8,5' -> '8.5', empty -> None."""
    if not raw or str(raw).strip() in ("", "nan", "None"):
        return None
    s = str(raw).strip().replace(",", ".")
    try:
        val = float(s)
        return f"{val:.2f}"
    except ValueError:
        return None


NOTA_COLUMNS = [f"nota{str(i).zfill(2)}" for i in range(1, 11)]
