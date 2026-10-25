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

## Verificação (2026-10-25)
- 407 testes passando em Python 3.11, 3.12 e 3.13.
- Distribuição: funcao 12, estabilidade 58, integracao 32, interferencia 9, desempenho 4, recursividade 9 (+ testes sem marca).
- Mutação: 33 mutações injetadas, 33 detectadas.
- `ruff check` e `ruff format --check` limpos.
