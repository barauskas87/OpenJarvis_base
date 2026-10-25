# LOG DE ALTERAÇÕES

Referência dos achados: `vetting/03_segunda_passada.md` (N1–N27) e `vetting/modulos/` (C1–C4).

## Corrigidos (patch em `patches/`)
| Achado | Peça | Correção |
|---|---|---|
| N1/N2 | tools/_stubs | negar por padrão; `is_local=False`; segredos mascarados em eventos |
| N4 | tools/shell_exec | ambiente mínimo, matar árvore de processos |
| N6 | security/capabilities | deny vence; padrão exige recurso |
| N10 | scheduler | falha em um item não aborta o lote |
| N11/N12 | memory/service | sem resposta na extração; revisão obrigatória |
| N13/N13b/N13c | agents/loop_guard | ping-pong por assinatura de chamada (**N13b/N13c: bugs novos, ausentes do relatório**) |
| N14/N15 | agents/native_react | observação delimitada e escapada; limite 8000 |
| N16 | security/scanner, rate_limiter | Python puro, validadores Luhn/CPF/CNPJ, máscara parcial |
| N17 | security/taint, injection_scanner | PT-BR, `</observation>`, acentos normalizados |
| N18 | scanner | Luhn |
| N19 | security/file_policy | bloqueia estado do Nó, caixa alta, mais nomes |
| N20 | mcp/* | allowlist de comando/host, ambiente mínimo, prefixo e confirmação |
| N21 | skills/executor | template estrutural, profundidade máx. 5 |
| N22 | skills/loader | assinatura e varredura de injeção |
| N23 | traces/collector | isolamento por thread, mascaramento |
| N24 | channels/telegram | só IDs autorizados |
| N25 | security/signing | chave privada 0600 |
| C1–C3 | http_request, ssrf | redirect revalidado, sem Authorization entre hosts, CGNAT etc. |
| C4 | — | peça `repl` excluída |

## Removido / não copiado
Rust, telemetria (posthog), instaladores, desktop/deploy, `repl`.

## Achado pelo CI no Windows
| Peça | Problema | Correção |
|---|---|---|
| tools/file_read | abrir diretório dá `PermissionError` no Windows, e a resposta era "Read error" em vez de "Not a file" | checagem `is_dir()` antes de abrir |
| Tests/test_ferramentas | 2 testes dependiam de `\n` (Windows grava `\r\n`) | gravação em bytes |

## Cliente fino para Android (decisão do dono)
| Peça | O que é |
|---|---|
| `servidor/` (novo) | API HTTPS: token com hash SHA-256 comparado em tempo constante, limites por token e por IP, teto de corpo (cabeçalho e leitura em pedaços), erros sem eco, máscara de segredos, histórico isolado por dono, concorrência limitada, recusa de exposição sem TLS |
| `android/nucleo/` (novo) | cliente Kotlin/JVM: só https, certificado fixo ou pins, sem redirecionamento, sem repetição de POST, teto de resposta, token fora das mensagens de erro |
| `android/app/` (novo) | app Compose + Keystore (compila no CI com `assembleDebug`; não executado em aparelho) |
| `contrato/` (novo) | exemplos e `openapi.json` lidos pelos testes de Python e de Kotlin |
| bug achado nos testes | `historico or HistoricoDeConversas()` descartava histórico vazio (objeto com `__len__`) |

## Achado pelo CI no Windows (2ª rodada)
| Peça | Problema | Correção |
|---|---|---|
| memory/store (upstream) | no Windows o bloqueio de bytes é obrigatório: duas instâncias criando o arquivo de lock ao mesmo tempo davam `PermissionError` na escrita do byte inicial, e o fato era perdido | `_garantir_byte_do_lock` tolera a corrida; arquivo sem buffer. Patch em `patches/memory__store.patch` |

## Verificação (2026-10-25)
- 487 testes Python passando em 3.11, 3.12 e 3.13 localmente e 3.10–3.13 em Linux/Windows no CI (407 antes da API + 80 da API).
- 52 testes Kotlin (núcleo), 5 deles contra o servidor Python real com TLS; o app Android compila no CI (`assembleDebug`), mas não foi executado em aparelho.
- Mutação: servidor 30/30; cliente Kotlin 16/16. A mutação achou 2 lacunas nos meus testes do cliente (teto de resposta e repetição automática de POST), já corrigidas.
- Distribuição: funcao 12, estabilidade 58, integracao 32, interferencia 9, desempenho 4, recursividade 9 (+ testes sem marca).
- Mutação: 33 mutações injetadas, 33 detectadas.
- `ruff check` e `ruff format --check` limpos.
