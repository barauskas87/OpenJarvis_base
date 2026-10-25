# MAPA DO SISTEMA — peças do OpenJarvis para o Nó Único

Projeto próprio (Bora Software / Siberian Tech). Origem: `open-jarvis/OpenJarvis`, copiada e corrigida
sem Rust, sem telemetria, sem instaladores. Nomes de pacotes mantidos (`openjarvis.*`) para facilitar
comparar com o upstream.

## Camadas
| Pasta (`src/openjarvis/`) | Função | Observação |
|---|---|---|
| `core/` | tipos, barramento de eventos, registro, caminhos | `events.py`, `types.py`, `paths.py` iguais ao upstream |
| `security/` | scanners, SSRF, capacidades, taint, injeção, assinatura, guardrails, limitador | tudo Python puro, negar por padrão |
| `tools/` | executor com política, `file_read`, `shell_exec`, `http_request`, adaptador MCP | `_stubs.py` é o núcleo |
| `agents/` | agente ReAct, guarda de laço | observação delimitada por `<observation>` |
| `skills/` | carregador (TOML/SKILL.md), executor, gerente, dependências | assinatura e varredura de injeção |
| `scheduler/` | cron/intervalo/uma vez + SQLite | lista de agentes/ferramentas permitidos |
| `mcp/` | transporte stdio/HTTP, cliente, loader, servidor | comando e host em lista permitida |
| `memory/`, `traces/` | fatos com revisão, rastros mascarados | |
| `engine/`, `channels/` | cliente OpenAI-compatível, Telegram | |

## Fluxo de uma chamada de ferramenta
limite de taxa → guarda de fronteira → capacidades (RBAC) → política de taint → confirmação →
execução com timeout (thread) → varredura de taint/injeção na saída → mascaramento de segredos.

## Testes (`Tests/`)
407 testes, marcados por dimensão: funcao, estabilidade, integracao, interferencia, desempenho,
recursividade. `pytest.ini` e `ruff.toml` na raiz.
