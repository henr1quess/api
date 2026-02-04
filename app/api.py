from typing import Any, Dict, Optional

from app.http import HttpClient, HttpResponse


def lista_turmas(http: HttpClient, periodo_sigla: str, mostrar_todas_as_turmas: bool = True) -> HttpResponse:
    params = {
        "periodo_sigla": str(periodo_sigla),
        "mostrar_todas_as_turmas": "true" if mostrar_todas_as_turmas else "false",
    }
    return http.request_json("GET", "/api/v0/lista_turmas/", params=params)


def diarios_por_turma(http: HttpClient, turma_id: int) -> HttpResponse:
    params = {"turma": str(turma_id)}
    return http.request_json("GET", "/api/v0/diarios/", params=params)


def correcao_prova(http: HttpClient, body: Dict[str, Any]) -> HttpResponse:
    return http.request_json("POST", "/api/v0/correcao_prova/", payload=body)
