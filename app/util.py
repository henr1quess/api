import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Dict, Any, List

import yaml


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_dirs(root: Path) -> None:
    (root / "data" / "inbox").mkdir(parents=True, exist_ok=True)
    (root / "data" / "out").mkdir(parents=True, exist_ok=True)
    (root / "data" / "logs").mkdir(parents=True, exist_ok=True)


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_env_required(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        raise ValueError(f"Faltando variável de ambiente {key} no .env")
    return val


def read_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        obj = yaml.safe_load(f)
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise ValueError(f"YAML precisa ser um dict no topo: {path}")
    return obj


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def write_json(path: Path, obj: Any) -> None:
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def read_csv(path: Path, delimiter: str = ";") -> List[Dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        return [row for row in reader]


def write_csv(path: Path, rows: Iterable[Dict[str, Any]], fieldnames: List[str], delimiter: str = ";") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})
