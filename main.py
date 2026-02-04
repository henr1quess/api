import sys
import traceback
from pathlib import Path

import yaml
from dotenv import load_dotenv

from app.util import (
    project_root,
    load_env_required,
    read_yaml,
    ensure_dirs,
    now_stamp,
)
from app.http import HttpClient
from app.routines.import_notas import run as run_import_notas
from app.routines.export_turmas import run as run_export_turmas
from app.routines.export_diarios import run as run_export_diarios


ROUTINES = {
    "import_notas": run_import_notas,
    "export_turmas": run_export_turmas,
    "export_diarios": run_export_diarios,
}


def load_active_config() -> dict:
    root = project_root()
    active_path = root / "config" / "active.yaml"
    if not active_path.exists():
        raise FileNotFoundError(f"Faltando {active_path}")
    return read_yaml(active_path)


def load_profile(profile_path_str: str) -> dict:
    root = project_root()
    profile_path = (root / profile_path_str).resolve()
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile não existe: {profile_path}")
    return read_yaml(profile_path)


def main():
    root = project_root()

    # Load .env (local only)
    load_dotenv(root / ".env")

    base_url = load_env_required("ERP_BASE_URL").rstrip("/")
    token = load_env_required("ERP_TOKEN").strip()

    ensure_dirs(root)

    active = load_active_config()
    routine_name = str(active.get("routine", "")).strip()
    profile_ref = str(active.get("profile", "")).strip()

    if not routine_name or routine_name not in ROUTINES:
        raise ValueError(f"active.yaml precisa ter routine válida. Opções: {sorted(ROUTINES.keys())}")

    if not profile_ref:
        raise ValueError("active.yaml precisa ter 'profile' apontando para um YAML em config/profiles/...")

    profile = load_profile(profile_ref)

    ctx = {
        "root": root,
        "base_url": base_url,
        "token": token,
        "out_dir": root / "data" / "out",
        "inbox_dir": root / "data" / "inbox",
        "logs_dir": root / "data" / "logs",
        "run_stamp": now_stamp(),
    }

    http = HttpClient(base_url=base_url, token=token)

    # Dispatch
    ROUTINES[routine_name](profile=profile, ctx=ctx, http=http)


if __name__ == "__main__":
    try:
        main()
        print("OK")
    except Exception as e:
        print("ERRO:", repr(e))
        traceback.print_exc()
        sys.exit(1)
