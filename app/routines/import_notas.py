from math import isnan
from pathlib import Path

from app.api import correcao_prova
from app.util import read_csv, write_csv, write_json


def _to_float(x):
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    # aceita vírgula como decimal na entrada
    s = s.replace(",", ".")
    try:
        v = float(s)
        if isnan(v):
            return None
        return v
    except ValueError:
        return None


def _chunk(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def run(profile: dict, ctx: dict, http):
    # destino
    turma_id = profile.get("turma_id")
    disciplina_id = profile.get("disciplina_id")
    fase_nota_id = profile.get("fase_nota_id")
    slot = str(profile.get("slot", "nota01")).strip()

    if turma_id in [None, ""] or disciplina_id in [None, ""] or fase_nota_id in [None, ""]:
        raise ValueError("Profile import_notas precisa de turma_id, disciplina_id, fase_nota_id")

    turma_id = int(turma_id)
    disciplina_id = int(disciplina_id)
    fase_nota_id = int(fase_nota_id)

    # policy
    write_policy = profile.get("write_policy", {}) if isinstance(profile.get("write_policy"), dict) else {}
    allow_write = bool(write_policy.get("allow_write", False))
    sobrescrever_nota = bool(write_policy.get("sobrescrever_nota", False))
    sobrescrever_nota_confirmada = bool(write_policy.get("sobrescrever_nota_confirmada", False))
    batch_size = int(write_policy.get("batch_size", 100))

    # input
    input_cfg = profile.get("input", {}) if isinstance(profile.get("input"), dict) else {}
    input_file = str(input_cfg.get("file", "")).strip()
    if not input_file:
        raise ValueError("Profile import_notas precisa de input.file (ex: notas.csv)")

    in_path = ctx["inbox_dir"] / input_file
    if not in_path.exists():
        raise FileNotFoundError(f"Arquivo de entrada não existe: {in_path}")

    rows = read_csv(in_path, delimiter=";")

    # espera colunas: matricula e nota (mínimo)
    normalized = []
    errors = []

    for idx, r in enumerate(rows, start=2):  # 2 por causa do header
        matricula = str(r.get("matricula", "")).strip()
        nota = _to_float(r.get("nota"))

        if not matricula:
            errors.append({"linha": idx, "matricula": "", "erro": "matricula vazia"})
            continue
        if nota is None:
            errors.append({"linha": idx, "matricula": matricula, "erro": "nota inválida"})
            continue

        normalized.append({"matricula": matricula, "nota_100": nota})

    out_base = ctx["out_dir"] / f"{ctx['run_stamp']}_import_notas_turma{turma_id}"

    # sempre exporta validação
    write_csv(out_base.with_name(out_base.name + "_normalized.csv"), normalized, fieldnames=["matricula", "nota_100"])
    write_csv(out_base.with_name(out_base.name + "_errors.csv"), errors, fieldnames=["linha", "matricula", "erro"])

    if errors:
        raise RuntimeError(f"Validação falhou: {len(errors)} erros. Veja o CSV de erros em data/out.")

    # prepara payload (dry-run)
    notas_payload = [{"matricula": n["matricula"], slot: float(n["nota_100"])} for n in normalized]
    body_base = {
        "turma_id": turma_id,
        "fase_nota_id": fase_nota_id,
        "disciplina_id": disciplina_id,
        "sobrescrever_nota": sobrescrever_nota,
        "sobrescrever_nota_confirmada": sobrescrever_nota_confirmada,
    }

    preview = {"endpoint": "/api/v0/correcao_prova/", "body_base": body_base, "slot": slot, "total": len(notas_payload)}
    write_json(out_base.with_name(out_base.name + "_preview.json"), preview)

    if not allow_write:
        # dry-run: não escreve
        return

    # write em batches
    results = []
    batch_num = 0

    for batch in _chunk(notas_payload, batch_size):
        batch_num += 1
        body = dict(body_base)
        body["notas"] = batch

        resp = correcao_prova(http=http, body=body)

        write_json(
            out_base.with_name(out_base.name + f"_resp_batch{batch_num}.json"),
            {"status": resp.status, "payload": resp.payload, "raw": resp.raw},
        )

        if resp.status >= 400:
            # marca todo batch como erro
            for it in batch:
                results.append({"matricula": it["matricula"], "status": "erro", "http_status": resp.status})
            continue

        for it in batch:
            results.append({"matricula": it["matricula"], "status": "ok", "http_status": resp.status})

    write_csv(out_base.with_name(out_base.name + "_result.csv"), results, fieldnames=["matricula", "status", "http_status"])
