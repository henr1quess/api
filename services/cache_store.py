"""Disk-based cache for API datasets.

Saves every GET result as CSV + Parquet + metadata JSON.
Provides deterministic cache keys, TTL per endpoint, and
manual refresh support.

Layout on disk:
    data_cache/
        csv/       <key>.csv
        parquet/   <key>.parquet
        meta/      <key>.json      (index / catalogue entry)
"""

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

# ═══════════════════════════════════════════════════════════════════
# TTL presets (hours)
# ═══════════════════════════════════════════════════════════════════
TTL_CADASTRO = 24.0
TTL_ACADEMICO = 12.0
TTL_FREQUENCIA = 4.0
TTL_FINANCEIRO = 12.0
TTL_DEFAULT = 8.0

ENDPOINT_TTL: Dict[str, float] = {
    "acesso_alunos": TTL_CADASTRO,
    "acesso_enturmacao": TTL_CADASTRO,
    "lista_turmas": TTL_CADASTRO,
    "lista_alunos": TTL_CADASTRO,
    "lista_responsaveis": TTL_CADASTRO,
    "lista_colaboradores": TTL_CADASTRO,
    "lista_unidades": TTL_CADASTRO,
    "lista_usuarios": TTL_CADASTRO,
    "enturmacao": TTL_CADASTRO,
    "enturmacao_com_detalhes": TTL_CADASTRO,
    "diarios": TTL_ACADEMICO,
    "lista_disciplina_turma": TTL_ACADEMICO,
    "diario_frequencia": TTL_FREQUENCIA,
    "financeiro_empresas": TTL_FINANCEIRO,
    "financeiro_servicos": TTL_FINANCEIRO,
    "financeiro_forma_recebimento": TTL_FINANCEIRO,
}


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _safe_filename(s: str) -> str:
    """Convert any string to a Windows-safe filename component."""
    safe = re.sub(r"[^a-zA-Z0-9_\-.]", "_", s)
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe or "unknown"


def _compute_key(
    base_url: str,
    endpoint: str,
    params: Optional[Dict],
    token: str,
) -> str:
    """Deterministic cache key: <readable_name>__<hash8>."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()[:8]
    blob = json.dumps(
        {
            "base_url": base_url,
            "endpoint": endpoint,
            "params": dict(sorted((params or {}).items())),
            "token_hash": token_hash,
        },
        sort_keys=True,
        default=str,
    )
    full_hash = hashlib.sha256(blob.encode()).hexdigest()[:8]
    return f"{_safe_filename(endpoint)}__{full_hash}"


def _ttl_for(endpoint_name: str) -> float:
    return ENDPOINT_TTL.get(_safe_filename(endpoint_name), TTL_DEFAULT)


# ═══════════════════════════════════════════════════════════════════
# DatasetMeta
# ═══════════════════════════════════════════════════════════════════

class DatasetMeta:
    """Read-only view on a cached dataset's metadata."""

    def __init__(self, data: Dict[str, Any]):
        self._d = data

    # properties
    key = property(lambda s: s._d.get("dataset_key", ""))
    endpoint = property(lambda s: s._d.get("endpoint", ""))
    params = property(lambda s: s._d.get("params", {}))
    timestamp = property(lambda s: s._d.get("timestamp", 0.0))
    timestamp_iso = property(lambda s: s._d.get("timestamp_iso", ""))
    ttl_hours = property(lambda s: s._d.get("ttl_hours", TTL_DEFAULT))
    rows = property(lambda s: s._d.get("rows", 0))
    columns = property(lambda s: s._d.get("columns", 0))
    csv_path = property(lambda s: s._d.get("csv_path", ""))
    parquet_path = property(lambda s: s._d.get("parquet_path", ""))

    def is_fresh(self) -> bool:
        age_h = (time.time() - self.timestamp) / 3600
        return age_h < self.ttl_hours

    def age_str(self) -> str:
        secs = time.time() - self.timestamp
        if secs < 60:
            return f"{int(secs)}s"
        if secs < 3600:
            return f"{int(secs / 60)}min"
        return f"{secs / 3600:.1f}h"


# ═══════════════════════════════════════════════════════════════════
# CacheStore
# ═══════════════════════════════════════════════════════════════════

class CacheStore:
    """Disk-backed cache: CSV + Parquet + metadata JSON per dataset."""

    def __init__(self, cache_dir: Optional[Path] = None):
        if cache_dir is None:
            cache_dir = Path(__file__).resolve().parent.parent / "data_cache"
        self.cache_dir = cache_dir
        self.csv_dir = cache_dir / "csv"
        self.parquet_dir = cache_dir / "parquet"
        self.meta_dir = cache_dir / "meta"
        self._ensure_dirs()

    def _ensure_dirs(self):
        for d in (self.csv_dir, self.parquet_dir, self.meta_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ── key builder ───────────────────────────────────────────────

    def make_key(
        self,
        base_url: str,
        endpoint: str,
        params: Optional[Dict] = None,
        token: str = "",
    ) -> str:
        return _compute_key(base_url, endpoint, params, token)

    # ── main entry point ──────────────────────────────────────────

    def get_dataset(
        self,
        key: str,
        endpoint: str,
        params: Optional[Dict],
        fetch_fn: Callable[[], List[Dict]],
        ttl_hours: Optional[float] = None,
        force_refresh: bool = False,
    ) -> Tuple[pd.DataFrame, DatasetMeta, bool]:
        """Return (DataFrame, meta, cache_hit).

        cache_hit=True  means data came from disk (may be stale).
        cache_hit=False means fresh data was fetched from the API.
        """
        if ttl_hours is None:
            ttl_hours = _ttl_for(endpoint)

        # 1) try cache (unless forced)
        if not force_refresh:
            cached = self._load(key)
            if cached is not None:
                return cached[0], cached[1], True

        # 2) fetch from API
        try:
            records = fetch_fn()
            df = pd.DataFrame(records) if records else pd.DataFrame()
            meta = self._save(key, endpoint, params, df, ttl_hours)
            return df, meta, False
        except Exception:
            # fetch failed – return stale cache if available
            cached = self._load(key)
            if cached is not None:
                return cached[0], cached[1], True
            raise  # no cache, no API → propagate error

    # ── persistence ───────────────────────────────────────────────

    def _meta_path(self, key: str) -> Path:
        return self.meta_dir / f"{key}.json"

    def _csv_path(self, key: str) -> Path:
        return self.csv_dir / f"{key}.csv"

    def _parquet_path(self, key: str) -> Path:
        return self.parquet_dir / f"{key}.parquet"

    def _save(
        self,
        key: str,
        endpoint: str,
        params: Optional[Dict],
        df: pd.DataFrame,
        ttl_hours: float,
    ) -> DatasetMeta:
        self._ensure_dirs()
        csv_p = self._csv_path(key)
        parquet_p = self._parquet_path(key)
        meta_p = self._meta_path(key)

        # CSV (always)
        df.to_csv(csv_p, index=False, sep=";", encoding="utf-8-sig")

        # Parquet (best-effort)
        parquet_ok = False
        try:
            df.to_parquet(parquet_p, index=False)
            parquet_ok = True
        except Exception:
            pass

        now = time.time()
        meta_data = {
            "dataset_key": key,
            "endpoint": endpoint,
            "params": params or {},
            "timestamp": now,
            "timestamp_iso": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            "ttl_hours": ttl_hours,
            "rows": len(df),
            "columns": len(df.columns),
            "column_names": list(df.columns),
            "csv_path": str(csv_p),
            "parquet_path": str(parquet_p) if parquet_ok else "",
        }
        with open(meta_p, "w", encoding="utf-8") as f:
            json.dump(meta_data, f, indent=2, ensure_ascii=False, default=str)

        return DatasetMeta(meta_data)

    def _load(self, key: str) -> Optional[Tuple[pd.DataFrame, DatasetMeta]]:
        meta_p = self._meta_path(key)
        if not meta_p.exists():
            return None
        try:
            with open(meta_p, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
        except Exception:
            return None

        meta = DatasetMeta(meta_data)

        # Parquet first (faster), fall back to CSV
        df = None
        pq = self._parquet_path(key)
        if pq.exists():
            try:
                df = pd.read_parquet(pq)
            except Exception:
                pass
        if df is None:
            csv_p = self._csv_path(key)
            if csv_p.exists():
                try:
                    df = pd.read_csv(csv_p, sep=";", encoding="utf-8-sig")
                except Exception:
                    return None
        if df is None:
            return None
        return df, meta

    # ── management ────────────────────────────────────────────────

    def clear(self, key: Optional[str] = None):
        """Clear one dataset or entire cache."""
        if key:
            for p in (self._csv_path(key), self._parquet_path(key), self._meta_path(key)):
                if p.exists():
                    p.unlink()
        else:
            import shutil
            for d in (self.csv_dir, self.parquet_dir, self.meta_dir):
                if d.exists():
                    shutil.rmtree(d)
            self._ensure_dirs()

    def list_datasets(self) -> List[DatasetMeta]:
        """List all cached datasets ordered by timestamp desc."""
        datasets = []
        for f in sorted(self.meta_dir.glob("*.json"), reverse=True):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    datasets.append(DatasetMeta(json.load(fh)))
            except Exception:
                pass
        return datasets
