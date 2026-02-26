"""Audit logging – records every significant action with run_id."""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


_LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"


def _ensure_dir() -> Path:
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return _LOGS_DIR


def generate_run_id() -> str:
    """Short unique run identifier."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short = uuid.uuid4().hex[:6]
    return f"{ts}_{short}"


def log_action(
    run_id: str,
    action: str,
    params: Optional[Dict[str, Any]] = None,
    result_counts: Optional[Dict[str, int]] = None,
    files: Optional[List[str]] = None,
    notes: str = "",
) -> None:
    """Append one audit entry to the daily log file (JSONL)."""
    _ensure_dir()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_path = _LOGS_DIR / f"audit_{today}.jsonl"

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "action": action,
        "params": _mask_secrets(params or {}),
        "result_counts": result_counts or {},
        "files": files or [],
        "notes": notes,
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def read_audit_log(date_str: Optional[str] = None) -> List[Dict]:
    """Read audit entries for a given date (default: today)."""
    _ensure_dir()
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_path = _LOGS_DIR / f"audit_{date_str}.jsonl"
    if not log_path.exists():
        return []
    entries: List[Dict] = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def list_audit_dates() -> List[str]:
    """Return available audit log dates."""
    _ensure_dir()
    dates = []
    for f in sorted(_LOGS_DIR.glob("audit_*.jsonl"), reverse=True):
        date_part = f.stem.replace("audit_", "")
        dates.append(date_part)
    return dates


def _mask_secrets(params: Dict) -> Dict:
    """Remove any key that looks like a secret/token."""
    masked = {}
    sensitive = {"token", "password", "secret", "authorization", "api_key"}
    for k, v in params.items():
        if k.lower() in sensitive:
            masked[k] = "***MASKED***"
        else:
            masked[k] = v
    return masked
