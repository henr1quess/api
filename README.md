# ERP School Automation (ActiveSoft/SIGA)

Projeto base para automações de integração com a API do ERP escolar (ActiveSoft/SIGA), com foco em rotinas manuais e troca de arquivos CSV para Excel. Este repositório inicia apenas com a estrutura mínima e documentação; **não há lógica implementada**.

## Objetivo
- Organizar rotinas de importação/exportação em CSV.
- Padronizar configuração via arquivos YAML e variáveis de ambiente.
- Manter segredos fora do Git usando `.env`.

## Setup
1. Copie o arquivo de exemplo e preencha com suas credenciais:
   ```bash
   cp .env.example .env
   ```
2. Edite o `.env` com as variáveis:
   - `ERP_BASE_URL`
   - `ERP_TOKEN`

> ⚠️ **Não commitar segredos**: o `.env` deve ficar fora do controle de versão.

## Configuração (YAML)
- `config/active.yaml`: seleciona a rotina e o profile ativo.
- `config/profiles/`: profiles com parâmetros por rotina (exemplo incluído).
- `config/mappings/`: reservado para mapeamentos futuros.

## Como rodar (futuro)
A execução será baseada no arquivo `config/active.yaml`, que define:
- A rotina ativa (`routine`)
- O profile YAML correspondente (`profile`)

Ainda não há execução real, mas a ideia é que `main.py` carregue `config/active.yaml` e dispare a rotina.

## CSV
- **Separador padrão:** `;`
- **Encoding:** UTF-8

## Pastas de dados
- **Entrada:** `data/inbox/`
- **Saída:** `data/out/`
- **Logs:** `data/logs/`

Essas pastas são para uso local e ficam ignoradas no Git.
