# PLATAFORMAS — Linux, Windows e Android

Decisão do dono do projeto: o Nó Único terá versão **Linux** e versão **Mobile (Android)**.
Windows já roda no CI, mas não é alvo declarado; fica como bônus.

## Situação de cada peça
| Peça | Linux | Windows | Android |
|---|---|---|---|
| `security/*` (scanners, SSRF, capacidades, taint, injeção, rate limit) | testado | testado | portável em lógica; precisa reescrita em Kotlin se o app não rodar Python |
| `tools/file_read`, `http_request` | testado | testado | idem; caminhos e permissões seguem o modelo de armazenamento do Android |
| `tools/shell_exec` | testado | **pulado** (POSIX) | **não existe** (sem shell de uso geral; app sandboxed) |
| `mcp/` transporte stdio | testado | **pulado** | **não existe** (não há subprocesso arbitrário); só transporte HTTP |
| `scheduler/` (SQLite + cron) | testado | testado | trocar por WorkManager/AlarmManager; o processo não fica vivo em segundo plano |
| `channels/telegram` | testado (sem laço real) | testado | pouco útil no aparelho; melhor ficar no servidor |
| `skills/`, `agents/`, `memory/`, `traces/` | testado | testado | depende da decisão abaixo |
| Chaves e segredos (`signing`, 0600) | testado | permissões POSIX puladas | usar Android Keystore, não arquivo |

## Decisão adotada: cliente fino
O app Android (Kotlin) fala por **HTTPS** com o Nó Linux, que roda estas peças. Nada de agente, ferramentas
ou segredos de modelo no aparelho. Consequências:
- `shell_exec`, MCP stdio, agendador e demais peças ficam **só no Nó**; o Android não precisa deles.
- O app guarda apenas: endereço do Nó, certificado (público) e o **token** (cifrado com o Android Keystore).
- Todo o comportamento de segurança continua nos 487+ testes Python; o contrato entre os dois lados é testado
  nos dois idiomas (ver `CONTRATO_API.md`).
- Código: servidor em `src/openjarvis/servidor/`; cliente em `../android/nucleo/` (Kotlin/JVM, testado);
  app em `../android/app/` (Compose; compila no CI, **ainda não foi executado em aparelho/emulador**).

## Regras para manter as três versões compatíveis
- Código com sistema operacional (processos, caminhos, permissões) fica em módulos pequenos e separados.
- Todo comportamento de segurança tem teste; o teste é o contrato que a versão Kotlin deve cumprir.
- O CI continua testando Linux e Windows; quando existir o app Android, acrescentar um job de build/teste dele.
