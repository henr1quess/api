# PRD – CEC Painel SigaWeb

## Objetivo
Painel web interno (Streamlit) para automacao de rotinas escolares integrando com a ActiveSoft SigaWeb API v0. Usuarios: coordenacao, secretaria, direcao.

## Escopo atual

### Modulo base
- Importacao de notas em lote (simulacao)
- Consulta de frequencia por diario com resumo
- Marcacao de frequencia via CSV (simulacao)
- Explorer de dados (consulta generica GET)
- Auditoria (logs de execucao)
- Cache persistente em disco (CSV + Parquet + metadata)
- Export CSV e Excel em todas as telas

### Modulo financeiro
- Dataset consolidado de boletos (410+ alunos × informacoes_boleto), cache permanente
- Dashboard executivo financeiro (KPIs: receita prevista/recebida, inadimplencia, ticket medio)
- Painel de cobranca com aging (faixas: 0-30, 31-60, 61-90, >90 dias)
- Deteccao de inconsistencias financeiras (regras confirmadas pelo usuario):
  - Valor divergente (pago a mais ou a menos)
  - Boletos de meses passados nao registrados
  - Alunos sem servico de mensalidade (deteccao por nome "Mens%")
- Relatorio de operacoes adversas (best-effort via API):
  - Titulos cancelados
  - Titulos estornados
  - Baixas retroativas (liquidacao registrada >7 dias apos pagamento)
- Pacote de exportacao mensal em Excel multiabas (6 abas)

### Modulo pedagogico
- Farol de risco de evasao/reprovacao:
  - Alunos com faltas excessivas (threshold configuravel, default 25%)
  - Alunos com notas criticas em 3+ disciplinas (threshold configuravel, default <6.0)
  - Risco combinado (faltas + notas)
  - Acao sugerida por nivel de risco
- Auditoria de diarios (engajamento docente):
  - Diarios sem frequencia na semana atual
  - Frequencia parcial (>20% nao registrado)
  - Compliance por turma (% diarios em dia)
- Consulta individual de boletim (via cache do farol de risco)

### Navegacao reorganizada
- 6 telas agrupadas por dominio:
  1. Inicio (cockpit com cache overview)
  2. Financeiro (5 abas: Executivo, Cobranca, Inconsistencias, Operacoes Adversas, Exportacoes)
  3. Academico (4 abas: Frequencia Consulta, Farol de Risco, Auditoria Diarios, Consulta Boletim)
  4. Operacoes (2 abas: Importar Notas, Frequencia Marcacao)
  5. Explorer API (consulta generica GET)
  6. Auditoria (logs)

## Nao-escopo (por enquanto)
- Execucao real de POST (modo simulacao apenas)
- Autenticacao de usuarios no painel
- Deploy em producao (Heroku, Docker etc.)
- Testes automatizados (pytest)
- CI/CD

## Requisitos funcionais

### Cache e persistencia
- [x] Salvar automaticamente todo GET em disco (CSV + Parquet)
- [x] Reusar dados salvos para renderizacao e export
- [x] Atualizar manualmente por endpoint (botao "Atualizar")
- [x] Persistir em disco para uso offline apos primeiro fetch
- [x] Cache key deterministica (base_url + path + params + token_hash)
- [x] Catalogo meta/index por dataset (JSON com timestamp, TTL, contagens)
- [x] TTL por tipo de endpoint (cadastro=24h, academico=12h, frequencia=4h)
- [x] TTL permanente para datasets consolidados (~10 anos, refresh so via botao)
- [x] UI mostra: cache hit/miss, idade, TTL, registros

### Financeiro
- [x] Fetch consolidado de boletos para todos os alunos ativos (progress bar)
- [x] Dataset enriquecido (join boletos x alunos x servicos + colunas derivadas)
- [x] KPIs executivos: receita prevista, recebida, inadimplencia R$ e %
- [x] Aging da carteira com buckets (Em dia, 1-30, 31-60, 61-90, >90)
- [x] Deteccao de inconsistencias (3 regras ativas)
- [x] Deteccao de operacoes adversas (best-effort, com transparencia)
- [x] Exportacao mensal multiabas (6 abas)

### Pedagogico
- [x] Fetch consolidado de frequencia por aluno (progress bar)
- [x] Fetch consolidado de boletins por aluno (progress bar)
- [x] Fetch consolidado de diarios por turma (progress bar)
- [x] Farol de risco com thresholds configuraveis (sliders)
- [x] Auditoria de diarios com metricas de compliance
- [x] Consulta individual de boletim (usa cache)

### Export
- [x] CSV (separador `;`, UTF-8 BOM)
- [x] Excel (`.xlsx`, nomes de aba sanitizados, multiplas abas)
- [x] JSON (payloads de simulacao)
- [x] Export usa dados ja carregados, sem request novo
- [x] Pacote financeiro mensal (Excel 6 abas)

### UI
- [x] Navegacao por sidebar com radio buttons (6 opcoes)
- [x] Session state para evitar reruns desnecessarios
- [x] Status de cache em cada dataset carregado
- [x] Botao de refresh manual por endpoint
- [x] Pagina inicial com overview do cache
- [x] Limpar cache global
- [x] Tabs internas por pagina (Financeiro: 5, Academico: 4, Operacoes: 2)

### Logs e auditoria
- [x] Audit log JSONL por dia com run_id
- [x] Token mascarado em logs
- [x] Viewer de auditoria com export

## Requisitos nao funcionais
- [x] Windows-safe: nomes de arquivo sem caracteres invalidos
- [x] Offline: dados em cache disponíveis sem conexao
- [x] Seguranca: token nunca salvo em claro (hash no cache key)
- [x] POST bloqueado por feature flag (WRITE_MODE_ENABLED)
- [x] Protecao a API: delay 150ms entre chamadas sequenciais
- [x] Retry com backoff exponencial (429/5xx)

## Decisoes tecnicas

| Decisao | Motivo |
|---------|--------|
| CSV + Parquet | CSV para abrir no Excel, Parquet para leitura rapida no app |
| Hash SHA256 no cache key | Determinisico, inclui token hash para separar ambientes |
| TTL por endpoint | Cadastros mudam pouco (24h), frequencia muda mais (4h) |
| TTL_PERMANENT (87600h) | Boletos e dados consolidados ficam em disco para sempre, refresh so via botao |
| index.json por dataset | Um JSON por dataset facilita leitura individual e limpeza |
| `_safe_filename()` | Garante nomes Windows-safe (sem `/`, `?`, `\` etc.) |
| Parquet best-effort | Se pyarrow nao disponivel, cai para CSV sem erro |
| `st.session_state` para refresh | Evita re-fetch em reruns do Streamlit |
| Fetch sequencial com delay | 410 alunos × 150ms = ~1.5min; protege a API contra rate limiting |
| `_find_column()` adaptativo | Busca campos por lista de candidatos; adapta a campos reais da API |
| Deteccao mensalidade `Mens%` | ILIKE por prefixo cobre variacoes: "Mens 2025", "Mens Integral" etc. |
| Operacoes adversas best-effort | Flag `detectavel_via_api` por tipo; avisa quando campo nao existe |
| Farol de risco configurable | Thresholds via sliders (% faltas, nota min); coordenacao ajusta conforme necessidade |
| Diarios turma-based | ~200 chamadas vs 410 per-student; mais eficiente para audit de compliance |

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
4. Sidebar mostra 6 opcoes: Inicio, Financeiro, Academico, Operacoes, Explorer API, Auditoria
5. Financeiro > Executivo > "Carregar boletos 2026" > progress bar > KPIs
6. Financeiro > Cobranca > tabela de aging
7. Financeiro > Inconsistencias > detectar inconsistencias > expanders por tipo
8. Financeiro > Operacoes Adversas > detectar > nota de transparencia
9. Financeiro > Exportacoes > gerar pacote Excel 6 abas
10. Academico > Frequencia Consulta > funciona como antes
11. Academico > Farol de Risco > carregar dados > sliders > metricas de risco
12. Academico > Auditoria Diarios > carregar diarios > compliance
13. Academico > Consulta Boletim > selecionar aluno > ver notas
14. Operacoes > Importar Notas / Freq Marcacao > funciona como antes
15. Explorer e Auditoria > sem mudanca de comportamento
16. Fechar e reabrir > dados carregam do disco sem chamada a API

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
- [x] Modulo financeiro (consolidacao, KPIs, aging, inconsistencias, operacoes adversas)
- [x] Modulo pedagogico (farol de risco, auditoria de diarios, consulta boletim)
- [x] Navegacao reorganizada em 6 dominios
- [x] Exportacao financeira mensal multiabas
- [x] TTL permanente para datasets consolidados
- [x] PRD atualizado

### A fazer
- [ ] Filtros avancados por dataset cacheado
- [ ] Modo escrita real (POST) com confirmacao
- [ ] Testes automatizados (pytest)
- [ ] CI/CD e deploy
