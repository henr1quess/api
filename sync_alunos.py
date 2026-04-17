"""Atualiza o cache de alunos buscando dados frescos da API.

Uso:
    python sync_alunos.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
import os

load_dotenv(ROOT / ".env")

from activesoft_client import ActiveSoftClient
from activesoft_client import endpoints as ep
from services.cache_store import CacheStore

base_url = os.getenv("ERP_BASE_URL", "").rstrip("/")
token = os.getenv("ERP_TOKEN", "").strip()

if not base_url or not token:
    print("ERRO: configure ERP_BASE_URL e ERP_TOKEN no .env")
    sys.exit(1)

client = ActiveSoftClient(base_url=base_url, token=token)
store = CacheStore(ROOT / "data_cache")

# O Streamlit usa o header Authorization completo como chave — replicamos aqui
token_for_key = f"Bearer {token}"

ENDPOINTS = [
    ("acesso_alunos",     "/api/v0/acesso/alunos/",     lambda: ep.acesso_alunos(client)),
    ("acesso_enturmacao", "/api/v0/acesso/enturmacao/", lambda: ep.acesso_enturmacao(client)),
]

print("Atualizando cadastros de alunos...\n")
for name, path, fn in ENDPOINTS:
    key = store.make_key(base_url, path, None, token_for_key)
    store.clear(key)
    df, meta, hit = store.get_dataset(key, name, None, fn, force_refresh=True)
    status = "cache" if hit else "API"
    print(f"  {name}: {meta.rows} registros ({status})")

print("\nConcluido. Recarregue o Streamlit para ver os dados atualizados.")
