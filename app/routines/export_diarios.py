from app.api import diarios_por_turma
from app.util import write_json, write_csv


def _pick(d: dict, keys: list):
    for k in keys:
        if k in d:
            return d.get(k)
    return None


def run(profile: dict, ctx: dict, http):
    turma_id = profile.get("turma_id")
    if turma_id in [None, ""]:
        raise ValueError("Profile export_diarios precisa de turma_id")

    turma_id_int = int(turma_id)

    resp = diarios_por_turma(http=http, turma_id=turma_id_int)

    out_base = ctx["out_dir"] / f"{ctx['run_stamp']}_diarios_turma{turma_id_int}"
    write_json(out_base.with_suffix(".json"), {"status": resp.status, "payload": resp.payload})

    if resp.status >= 400:
        raise RuntimeError(f"Erro API diarios: status={resp.status}")

    items = resp.payload
    if isinstance(items, dict):
        for k in ["results", "data", "items", "diarios", "itens"]:
            if isinstance(items.get(k), list):
                items = items[k]
                break

    if not isinstance(items, list):
        raise ValueError("Resposta inesperada de diários (não é lista)")

    # resumo (trincas)
    uniq = {}
    for d in items:
        if not isinstance(d, dict):
            continue
        tid = _pick(d, ["turma_id", "turma", "id_turma"])
        did = _pick(d, ["disciplina_id", "disciplina", "id_disciplina"])
        fid = _pick(d, ["fase_nota_id", "fase_nota", "id_fase_nota"])
        key = (tid, did, fid)
        if key not in uniq:
            uniq[key] = {"turma_id": tid, "disciplina_id": did, "fase_nota_id": fid}

    rows = list(uniq.values())
    write_csv(out_base.with_suffix(".csv"), rows, fieldnames=["turma_id", "disciplina_id", "fase_nota_id"])
