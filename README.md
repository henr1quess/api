# ERP School Automation (ActiveSoft/SIGA)

Toolkit mínimo para automações de integração com a API do ERP escolar (ActiveSoft/SIGA), com foco em rotinas manuais e troca de arquivos CSV para Excel.

## Objetivo
- Organizar rotinas de importação/exportação em CSV.
- Padronizar configuração via arquivos YAML e variáveis de ambiente.
- Manter segredos fora do Git usando `.env`.

## Instalação
1. Crie e ative um ambiente virtual (opcional, recomendado).
2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

## Configuração do `.env`
1. Copie o arquivo de exemplo e preencha com suas credenciais:
   ```bash
   cp .env.example .env
   ```
2. Edite o `.env` com as variáveis:
   - `ERP_BASE_URL` (ex: `https://seu-erp.com.br`)
   - `ERP_TOKEN`

> ⚠️ **Não commitar segredos**: o `.env` deve ficar fora do controle de versão.

## Configuração (YAML)
- `config/active.yaml`: seleciona a rotina e o profile ativo.
- `config/profiles/`: profiles com parâmetros por rotina.
- `config/mappings/`: reservado para mapeamentos futuros.

### Exemplo de `config/active.yaml`
```yaml
routine: export_turmas
profile: config/profiles/export_turmas_2025.yaml
```

## Como rodar (manual, sem CLI)
Com a configuração pronta, execute:
```bash
python main.py
```
O script lê `config/active.yaml`, carrega o profile apontado, carrega o `.env` e executa a rotina indicada.

## Rotinas disponíveis
### 1) export_turmas
Chama `GET /api/v0/lista_turmas/?periodo_sigla=...&mostrar_todas_as_turmas=true` e exporta CSV em `data/out`.

Profile mínimo (`config/profiles/export_turmas_2025.yaml`):
```yaml
periodo_sigla: "2025"
```

### 2) export_diarios
Chama `GET /api/v0/diarios/?turma=...` e salva:
- JSON completo
- CSV resumido com `turma_id`, `disciplina_id`, `fase_nota_id`

Profile mínimo (`config/profiles/export_diarios_turma93.yaml`):
```yaml
turma_id: 93
```

### 3) import_notas
Lê um CSV de entrada em `data/inbox` (separador `;`), normaliza as notas para `float` e prepara o payload para `POST /api/v0/correcao_prova/`.

- **Dry-run por padrão**: se `allow_write=false`, não faz POST, apenas gera preview em `data/out`.
- Se `allow_write=true`, faz POST em batches, salva respostas em JSON e gera `result.csv` com status por matrícula.

Profile mínimo (`config/profiles/import_notas_turma93.yaml`):
```yaml
turma_id: 93
disciplina_id: 12
fase_nota_id: 1608
slot: "nota01"

input:
  file: "notas.csv"

write_policy:
  allow_write: false
  sobrescrever_nota: false
  sobrescrever_nota_confirmada: false
  batch_size: 100
```

Template de entrada (`data/inbox/notas.csv`):
```csv
matricula;nota
000123;87,5
000124;92
```

## CSV
- **Separador padrão:** `;`
- **Encoding:** UTF-8 com BOM (`utf-8-sig`, compatível com Excel no Windows)

## Pastas de dados
- **Entrada:** `data/inbox/`
- **Saída:** `data/out/`
- **Logs:** `data/logs/`

Essas pastas são para uso local e ficam ignoradas no Git.
