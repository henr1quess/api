# CEC – Painel SigaWeb

Painel web interno (Streamlit) para automacao de rotinas escolares integrando com a **ActiveSoft SigaWeb API v0**.

## Funcionalidades

| Tela | Descricao | Tipo |
|------|-----------|------|
| Importar Notas | Upload CSV, validacao, simulacao de POST `/correcao_prova/` | Simulacao |
| Frequencia – Consulta | Consulta de frequencia por diario com resumo | GET + Export |
| Frequencia – Marcacao | Upload CSV, validacao, simulacao de POST `/marcar_frequencia_aluno/` | Simulacao |
| Explorer de Dados | Consulta generica a qualquer endpoint GET | GET + Export |
| Auditoria | Visualizacao de logs de execucao | Leitura |

## Arquitetura

```
streamlit_app.py          # Entry point
activesoft_client/         # SDK interno
  http_client.py           # HTTP client (Bearer, retry, paginacao)
  endpoints.py             # Wrappers de endpoints
services/                  # Regras de negocio
  validators.py            # Modelos Pydantic
  grades.py                # Importacao de notas
  frequency.py             # Frequencia
  export_utils.py          # CSV / Excel / JSON
  audit.py                 # Auditoria (JSONL)
ui/                        # Paginas Streamlit
  components.py            # Componentes compartilhados
  page_home.py
  page_grades.py
  page_freq_query.py
  page_freq_mark.py
  page_explorer.py
  page_audit.py
templates/                 # CSVs modelo
exports/                   # Saida gerada
logs/                      # Audit logs (JSONL)
```

## Setup

1. Clone o repositorio e entre no diretorio.

2. Crie um ambiente virtual e instale dependencias:
```bash
python -m venv .venv
.venv\Scripts\activate     # Windows
pip install -r requirements.txt
```

3. Configure o `.env`:
```bash
copy .env.example .env
```
Edite com suas credenciais:
```
ERP_BASE_URL=https://siga.activesoft.com.br
ERP_TOKEN=seu_token_aqui
WRITE_MODE_ENABLED=false
```

4. Execute:
```bash
streamlit run streamlit_app.py
```

## CLI legado (main.py)

O toolkit original via linha de comando continua disponivel:
```bash
python main.py
```
Leia `config/active.yaml` para selecionar rotina e profile.

## Seguranca

- Token nunca aparece em logs nem exports (mascarado automaticamente).
- `WRITE_MODE_ENABLED=false` por padrao – POST bloqueado.
- Toda acao gera log de auditoria com `run_id`.

## Exports

Todas as telas permitem exportar em:
- **CSV** (separador `;`, UTF-8 BOM)
- **Excel** (`.xlsx`, multiplas abas quando aplicavel)
- **JSON** (payloads de simulacao)

## Templates

- `templates/modelo_notas.csv` – modelo para importacao de notas
- `templates/modelo_frequencia_marcacao.csv` – modelo para marcacao de frequencia
