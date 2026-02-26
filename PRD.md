# PRD – CEC Painel SigaWeb

## Objetivo
Painel web interno (Streamlit) para automacao de rotinas escolares integrando com a ActiveSoft SigaWeb API v0. Usuarios: coordenacao, secretaria, direcao.

## Escopo atual
- Importacao de notas em lote (simulacao)
- Consulta de frequencia por diario com resumo
- Marcacao de frequencia via CSV (simulacao)
- Explorer de dados (consulta generica GET)
- Auditoria (logs de execucao)
- Cache persistente em disco (CSV + Parquet + metadata)
- Export CSV e Excel em todas as telas

## Nao-escopo (por enquanto)
- Dashboards e graficos (arquitetura pronta, mas nao implementado)
- Execucao real de POST (modo simulacao apenas)
- Autenticacao de usuarios no painel
- Deploy em producao (Heroku, Docker etc.)

## Requisitos funcionais

### Cache e persistencia
- [x] Salvar automaticamente todo GET em disco (CSV + Parquet)
- [x] Reusar dados salvos para renderizacao e export
- [x] Atualizar manualmente por endpoint (botao "Atualizar")
- [x] Persistir em disco para uso offline apos primeiro fetch
- [x] Cache key deterministica (base_url + path + params + token_hash)
- [x] Catalogo meta/index por dataset (JSON com timestamp, TTL, contagens)
- [x] TTL por tipo de endpoint (cadastro=24h, academico=12h, frequencia=4h)
- [x] UI mostra: cache hit/miss, idade, TTL, registros

### Export
- [x] CSV (separador `;`, UTF-8 BOM)
- [x] Excel (`.xlsx`, nomes de aba sanitizados, multiplas abas)
- [x] JSON (payloads de simulacao)
- [x] Export usa dados ja carregados, sem request novo

### UI
- [x] Navegacao por sidebar com radio buttons
- [x] Session state para evitar reruns desnecessarios
- [x] Status de cache em cada dataset carregado
- [x] Botao de refresh manual por endpoint
- [x] Pagina inicial com overview do cache
- [x] Limpar cache global

### Logs e auditoria
- [x] Audit log JSONL por dia com run_id
- [x] Token mascarado em logs
- [x] Viewer de auditoria com export

## Requisitos nao funcionais
- [x] Windows-safe: nomes de arquivo sem caracteres invalidos
- [x] Offline: dados em cache disponíveis sem conexao
- [x] Seguranca: token nunca salvo em claro (hash no cache key)
- [x] POST bloqueado por feature flag (WRITE_MODE_ENABLED)

## Decisoes tecnicas

| Decisao | Motivo |
|---------|--------|
| CSV + Parquet | CSV para abrir no Excel, Parquet para leitura rapida no app |
| Hash SHA256 no cache key | Determinisico, inclui token hash para separar ambientes |
| TTL por endpoint | Cadastros mudam pouco (24h), frequencia muda mais (4h) |
| index.json por dataset | Um JSON por dataset facilita leitura individual e limpeza |
| `_safe_filename()` | Garante nomes Windows-safe (sem `/`, `?`, `\` etc.) |
| Parquet best-effort | Se pyarrow nao disponivel, cai para CSV sem erro |
| `st.session_state` para refresh | Evita re-fetch em reruns do Streamlit |

## Bugs corrigidos

| Bug | Causa raiz | Fix |
|-----|-----------|-----|
| AttributeError em Importar Notas | `diarios` retorna `disciplina: int`, codigo tentava `.get()` em int | `parse_diarios()` le campos flat (`disciplina`, `nome_disciplina`) |
| AttributeError em Frequencia Consulta | Mesmo problema: `diarios` com campos flat | `format_diario_label()` le campos flat |
| ValueError Excel sheet name `/` | Endpoint `acesso/alunos` usado como nome de aba | `_sanitize_sheet_name()` remove caracteres invalidos |
| Turma dropdown mostrando "ID 138" | `lista_turmas` retorna `nome`, codigo buscava `nome_turma` | `format_turma_label()` tenta `nome_turma_completo`, `nome_turma`, `nome` |
| Presenca nao detectada | Bullet `U+2022` podia vir como variantes | `_classify_presence()` aceita multiplos codigos |

## Como testar (somente GET)
1. `pip install -r requirements.txt`
2. `streamlit run streamlit_app.py`
3. Inserir token na sidebar
4. Navegar pelas telas — primeira vez faz fetch e popula cache
5. Navegar novamente — deve mostrar "Cache" e nao fazer request
6. Clicar "Atualizar" — deve fazer request e mostrar "API"
7. Verificar `data_cache/csv/` e `data_cache/parquet/` no disco
8. Verificar `data_cache/meta/` para metadados de cada dataset

## Tarefas

### Feitas
- [x] SDK ActiveSoft (http_client, endpoints, paginacao)
- [x] Cache persistente (CSV + Parquet + meta)
- [x] Fix: AttributeError diarios (campos flat)
- [x] Fix: Excel sheet name sanitization
- [x] Fix: Turma label (campo `nome`)
- [x] Fix: Presence code detection
- [x] UI: cache status em cada fetch
- [x] UI: botao refresh manual
- [x] UI: overview de cache na home
- [x] Audit logging
- [x] PRD criado

### A fazer
- [ ] Dashboards e graficos (usando dados do cache)
- [ ] Filtros avancados por dataset cacheado
- [ ] Modo escrita real (POST) com confirmacao
- [ ] Testes automatizados (pytest)
- [ ] CI/CD e deploy
