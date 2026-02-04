from pathlib import Path

from app.api import lista_turmas
from app.util import write_json, write_csv


def run(profile: dict, ctx: dict, http):
    periodo = str(profile.get("periodo_sigla", "")).strip()
    if not periodo:
        raise ValueError("Profile export_turmas precisa de periodo_sigla")

    resp = lista_turmas(http=http, periodo_sigla=periodo, mostrar_todas_as_turmas=True)

    out_base = ctx["out_dir"] / f"{ctx['run_stamp']}_turmas_{periodo}"
    write_json(out_base.with_suffix(".json"), {"status": resp.status, "payload": resp.payload})

    if resp.status >= 400:
        raise RuntimeError(f"Erro API turmas: status={resp.status}")

    items = resp.payload
    if isinstance(items, dict):
        # tenta chaves comuns
        for k in ["results", "data", "items", "turmas", "itens"]:
            if isinstance(items.get(k), list):
                items = items[k]
                break

    if not isinstance(items, list):
        raise ValueError("Resposta inesperada de lista_turmas (não é lista)")

    rows = []
    for t in items:
        if not isinstance(t, dict):
            continue
        rows.append({
            "id": t.get("id") or t.get("turma_id") or t.get("pk"),
            "descricao": t.get("descricao") or t.get("nome") or t.get("sigla") or t.get("label"),
        })

    write_csv(out_base.with_suffix(".csv"), rows, fieldnames=["id", "descricao"])
