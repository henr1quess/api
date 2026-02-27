"""Endpoint wrappers for all SigaWeb v0 endpoints used by the app.

Convention:
- GET endpoints return data directly.
- POST endpoints only BUILD the payload dict (simulation).
  Actual sending is gated by the write-mode flag.
"""

from typing import Any, Dict, List, Optional

from .http_client import ActiveSoftClient


# ═══════════════════════════════════════════════════════════════════
# GET – Access / entry control
# ═══════════════════════════════════════════════════════════════════

def acesso_alunos(client: ActiveSoftClient) -> List[Dict]:
    """Active students (official course, current year)."""
    return client.get_all("/api/v0/acesso/alunos/")


def acesso_enturmacao(client: ActiveSoftClient) -> List[Dict]:
    """id_aluno + id_turma for active students."""
    return client.get_all("/api/v0/acesso/enturmacao/")


def acesso_vinculo_responsavel(client: ActiveSoftClient) -> List[Dict]:
    return client.get_all("/api/v0/acesso/vinculo_aluno_responsavel_liberado/")


def listar_frequencia_aluno(
    client: ActiveSoftClient,
    aluno_id: int,
    data_inicial: Optional[str] = None,
    data_final: Optional[str] = None,
    tipo_marcacao: Optional[str] = None,
) -> Any:
    params: Dict[str, Any] = {"aluno_id": aluno_id}
    if data_inicial:
        params["data_inicial"] = data_inicial
    if data_final:
        params["data_final"] = data_final
    if tipo_marcacao:
        params["tipo_marcacao"] = tipo_marcacao
    return client.get_all("/api/v0/listar_frequencia_aluno/", params=params)


# ═══════════════════════════════════════════════════════════════════
# GET – Academic
# ═══════════════════════════════════════════════════════════════════

def lista_turmas(
    client: ActiveSoftClient,
    periodo_sigla: Optional[str] = None,
    todas: bool = True,
) -> List[Dict]:
    params: Dict[str, Any] = {
        "mostrar_todas_as_turmas": "true" if todas else "false",
    }
    if periodo_sigla:
        params["periodo_sigla"] = periodo_sigla
    return client.get_all("/api/v0/lista_turmas/", params=params)


def diarios(client: ActiveSoftClient, turma_id: int) -> List[Dict]:
    return client.get_all("/api/v0/diarios/", params={"turma": str(turma_id)})


def diario_frequencia(client: ActiveSoftClient, diario_id: int) -> List[Dict]:
    return client.get_all(
        "/api/v0/diario_frequencia/", params={"diario": str(diario_id)}
    )


def lista_disciplina_turma(
    client: ActiveSoftClient, periodo: Optional[str] = None
) -> List[Dict]:
    params: Dict[str, Any] = {}
    if periodo:
        params["periodo"] = periodo
    return client.get_all("/api/v0/lista_disciplina_turma/", params=params)


def detalhe_boletim(
    client: ActiveSoftClient,
    aluno_id: int,
    turma_id: Optional[int] = None,
    turmas_ativas: Optional[bool] = None,
) -> Any:
    params: Dict[str, Any] = {"aluno_id": aluno_id}
    if turma_id is not None:
        params["turma_id"] = turma_id
    if turmas_ativas is not None:
        params["turmas_ativas"] = "true" if turmas_ativas else "false"
    return client.get("/api/v0/detalhe_boletim/", params=params)


# ═══════════════════════════════════════════════════════════════════
# GET – People / enrollment
# ═══════════════════════════════════════════════════════════════════

def lista_alunos(client: ActiveSoftClient) -> List[Dict]:
    return client.get_all("/api/v0/lista_alunos/")


def lista_responsaveis(client: ActiveSoftClient) -> List[Dict]:
    return client.get_all("/api/v0/lista_responsaveis/")


def lista_colaboradores(client: ActiveSoftClient) -> List[Dict]:
    return client.get_all("/api/v0/lista_colaboradores/")


def lista_unidades(client: ActiveSoftClient) -> List[Dict]:
    return client.get_all("/api/v0/lista_unidades/")


def lista_usuarios(client: ActiveSoftClient) -> List[Dict]:
    return client.get_all("/api/v0/lista_usuarios/")


def enturmacao(client: ActiveSoftClient, **filters: Any) -> List[Dict]:
    return client.get_all("/api/v0/enturmacao/", params=filters)


def enturmacao_detalhes(client: ActiveSoftClient, **filters: Any) -> List[Dict]:
    return client.get_all("/api/v0/enturmacao_com_detalhes/", params=filters)


# ═══════════════════════════════════════════════════════════════════
# GET – Finance
# ═══════════════════════════════════════════════════════════════════

def financeiro_empresas(client: ActiveSoftClient) -> List[Dict]:
    return client.get_all("/api/v0/financeiro/empresas/")


def financeiro_servicos(client: ActiveSoftClient) -> List[Dict]:
    return client.get_all("/api/v0/financeiro/servicos/")


def financeiro_forma_recebimento(client: ActiveSoftClient) -> List[Dict]:
    return client.get_all("/api/v0/financeiro/forma_recebimento/")


def financeiro_calculo_multa_juros(client: ActiveSoftClient) -> List[Dict]:
    return client.get_all("/api/v0/financeiro/calculo_multa_juros/")


def informacoes_boleto(
    client: ActiveSoftClient, id_aluno: int, **kw: Any
) -> List[Dict]:
    params: Dict[str, Any] = {"id_aluno": id_aluno, **kw}
    return client.get_all("/api/v0/informacoes_boleto/", params=params)


# ═══════════════════════════════════════════════════════════════════
# POST – payload builders (SIMULATION ONLY – never executes)
# ═══════════════════════════════════════════════════════════════════

def build_correcao_prova(
    turma_id: int,
    fase_nota_id: int,
    disciplina_id: int,
    notas: List[Dict],
    sobrescrever_nota: bool = False,
    sobrescrever_nota_confirmada: bool = False,
) -> Dict:
    """Build CorrecaoProva payload WITHOUT sending."""
    return {
        "turma_id": turma_id,
        "fase_nota_id": fase_nota_id,
        "disciplina_id": disciplina_id,
        "sobrescrever_nota": sobrescrever_nota,
        "sobrescrever_nota_confirmada": sobrescrever_nota_confirmada,
        "notas": notas,
    }


def build_marcacao_frequencia(
    data_hora: str,
    tipo: str,
    matricula: str,
    id_responsavel: Optional[int] = None,
    comentario: Optional[str] = None,
) -> Dict:
    """Build MarcacaoFrequencia payload WITHOUT sending."""
    payload: Dict[str, Any] = {
        "data_hora": data_hora,
        "tipo_entrada_saida": tipo,
        "matricula": matricula,
    }
    if id_responsavel is not None:
        payload["id_responsavel_acompanhante"] = id_responsavel
    if comentario:
        payload["comentario"] = comentario[:50]
    return payload


# ═══════════════════════════════════════════════════════════════════
# Generic explorer helper
# ═══════════════════════════════════════════════════════════════════

# Registry of available GET endpoints for the explorer page.
EXPLORER_ENDPOINTS: Dict[str, Dict[str, Any]] = {
    "acesso/alunos": {
        "path": "/api/v0/acesso/alunos/",
        "description": "Alunos ativos (acesso)",
        "params": [],
    },
    "acesso/enturmacao": {
        "path": "/api/v0/acesso/enturmacao/",
        "description": "Enturmacao (acesso)",
        "params": [],
    },
    "lista_turmas": {
        "path": "/api/v0/lista_turmas/",
        "description": "Turmas",
        "params": ["periodo_sigla", "mostrar_todas_as_turmas"],
    },
    "lista_alunos": {
        "path": "/api/v0/lista_alunos/",
        "description": "Alunos (completo)",
        "params": [],
    },
    "lista_responsaveis": {
        "path": "/api/v0/lista_responsaveis/",
        "description": "Responsaveis",
        "params": [],
    },
    "lista_colaboradores": {
        "path": "/api/v0/lista_colaboradores/",
        "description": "Colaboradores",
        "params": [],
    },
    "lista_unidades": {
        "path": "/api/v0/lista_unidades/",
        "description": "Unidades",
        "params": [],
    },
    "lista_usuarios": {
        "path": "/api/v0/lista_usuarios/",
        "description": "Usuarios",
        "params": [],
    },
    "diarios": {
        "path": "/api/v0/diarios/",
        "description": "Diarios de turma",
        "params": ["turma"],
    },
    "diario_frequencia": {
        "path": "/api/v0/diario_frequencia/",
        "description": "Frequencia de diario",
        "params": ["diario"],
    },
    "lista_disciplina_turma": {
        "path": "/api/v0/lista_disciplina_turma/",
        "description": "Disciplinas por turma",
        "params": ["periodo"],
    },
    "enturmacao": {
        "path": "/api/v0/enturmacao/",
        "description": "Enturmacao",
        "params": ["periodo", "turma", "aluno"],
    },
    "enturmacao_com_detalhes": {
        "path": "/api/v0/enturmacao_com_detalhes/",
        "description": "Enturmacao detalhada",
        "params": ["periodo", "turma", "aluno"],
    },
    "financeiro/empresas": {
        "path": "/api/v0/financeiro/empresas/",
        "description": "Empresas (financeiro)",
        "params": [],
    },
    "financeiro/servicos": {
        "path": "/api/v0/financeiro/servicos/",
        "description": "Servicos (financeiro)",
        "params": [],
    },
    "financeiro/forma_recebimento": {
        "path": "/api/v0/financeiro/forma_recebimento/",
        "description": "Formas de recebimento",
        "params": [],
    },
    "financeiro/calculo_multa_juros": {
        "path": "/api/v0/financeiro/calculo_multa_juros/",
        "description": "Calculo de multa e juros",
        "params": [],
    },
    "informacoes_boleto": {
        "path": "/api/v0/informacoes_boleto/",
        "description": "Informacoes de boleto por aluno",
        "params": ["id_aluno"],
    },
    "detalhe_boletim": {
        "path": "/api/v0/detalhe_boletim/",
        "description": "Detalhe do boletim por aluno",
        "params": ["aluno_id", "turma_id", "turmas_ativas"],
    },
    "listar_frequencia_aluno": {
        "path": "/api/v0/listar_frequencia_aluno/",
        "description": "Frequencia do aluno",
        "params": ["aluno_id", "data_inicial", "data_final", "tipo_marcacao"],
    },
}
