# 03 — Segunda passada: módulos que serão aproveitados

Mesmo commit `0ec344454de38525f3cfc52a8e06012e18871a7b`. Mesma regra: nada executado, instalado ou importado; só leitura. Nesta passada li **arquivo inteiro, linha a linha**, os módulos abaixo (≈ 8,4 mil linhas). Onde digo "li inteiro" é literal.

## 1. Cobertura

**Li inteiros (linha a linha):**
`agents/native_react.py` (367), `agents/loop_guard.py` (243), `agents/prompt_loader.py` (84), `agents/_stubs.py` (510), `tools/_stubs.py` (657), `tools/mcp_adapter.py` (75), `tools/file_read.py` (144), `tools/_paths.py` (38), `skills/parser.py`, `types.py`, `loader.py`, `executor.py`, `tool_adapter.py`, `manager.py`, `dependency.py` (1-80), `importer.py` (60-273), `overlay.py`, `index.py`, `tool_translator.py`, `security.py`, `__init__.py`, `scheduler/scheduler.py` (341), `scheduler/store.py` (167), `memory/store.py` (456), `memory/service.py` (332), `memory/extractor.py` (155), `mcp/client.py` (154), `mcp/loader.py` (150), `mcp/transport.py` (406), `mcp/server.py` (partes), `security/taint.py` (143), `security/file_policy.py` (98), `security/signing.py` (132), `security/scanner.py` (148), `security/injection_scanner.py` (196), `security/capabilities.py` (345), `security/boundary.py` (139), `security/guardrails.py` (330), `security/ssrf.py` (187), `engine/_openai_compat.py` (341), `engine/_base.py` (130), `engine/_stubs.py` (140), `engine/_http_async.py` (128), `channels/telegram.py` (456), `channels/_stubs.py` (98), `core/events.py` (212), `core/registry.py` (189), `core/types.py` (317), `rust/crates/openjarvis-security/src/ssrf.rs` (1-140).

**Li em parte:** `scheduler/tools.py` (linhas 14-112 de 350), `security/rate_limiter.py` (1-80), `security/runtime.py` (1-120), `security/file_utils.py` (1-60), `security/audit.py` (trechos), `traces/collector.py` (1-283, lido), `traces/store.py` (só esquema), `skills/data/*.toml` (varredura de `tool_name`; li `backup-files.toml`), `intelligence/model_catalog.py` (só `resolve_model_id_for_engine`).

**Não li (ficam como pendência):** `agents/executor.py` (991) e `agents/manager.py` (872), que são o runtime de "agentes gerenciados" (não precisa copiar); `mcp/protocol.py` (145); `scheduler/tools.py` 113-350; `security/_stubs.py`, `types.py`; `sessions/*`; `traces/store.py` e `analyzer.py`; `tools/storage/*`; `skills/sources/*`; `engine/ollama.py`, `engine/_async_loop.py`; `core/config.py` (2000+ linhas, só trechos); `rust/` além de `shell.rs`, `http_tools.rs` e `ssrf.rs`.

## 2. Decisão por peça (revisada)

Legenda de "puxa": o que a peça arrasta quando copiada.

| Peça | Arquivos | Veredito revisado | Patches obrigatórios | Puxa (escondido) |
|---|---|---|---|---|
| Agente ReAct | `agents/native_react.py`, `agents/_stubs.py`, `agents/prompt_loader.py` | **adaptado** | N13, N14, N15 | `core.config.load_config` (`agents/_stubs.py:98,230,457`), `core.registry`, `core.events`, `tools/_stubs.py` |
| Loop guard | `agents/loop_guard.py` | **adaptado** | N13 | Rust opcional (`:57-69`), tem fallback Python |
| Executor de ferramentas | `tools/_stubs.py` | **adaptado** | N12 | `security.taint` (puro Python), `security.capabilities` (**exige Rust**), `security.injection_scanner` (tem fallback) |
| Skills (núcleo) | `skills/parser.py`, `types.py`, `executor.py`, `tool_adapter.py`, `manager.py`, `dependency.py`, `overlay.py`, `security.py` | **adaptado** | N2, N4, N5, N6 | `yaml` (não declarado), `learning.agents.skill_discovery` só em `discover_from_traces` (não copiar) |
| Skills (carga/assinatura) | `skills/loader.py` | **adaptado** | N1, N5 | `security.signing` → `cryptography` |
| Skills (importação externa) | `skills/importer.py`, `index.py`, `sources/*`, `tool_translator.py` | **rejeitado por enquanto** | N1, N3, N4, N7, N8 | git de terceiros |
| Scheduler | `scheduler/scheduler.py`, `store.py` | **adaptado** | N10 | `croniter`; `tzdata` no Windows |
| Ferramentas do scheduler | `scheduler/tools.py` | **adaptado** | N11 | — |
| Memória (armazém) | `memory/store.py` | **aprovado** | nenhum | só `core.paths`, `core.registry`. Windows ok (`:28-71,93-124`) |
| Memória (serviço) | `memory/service.py`, `extractor.py` | **adaptado** | N21 | `security.injection_scanner` |
| MCP | `mcp/client.py`, `transport.py`, `loader.py`, `server.py`, `tools/mcp_adapter.py` | **adaptado** | N20 | `httpx`; `MCPServer` auto-descobre ferramentas |
| Guardrails | `security/taint.py`, `file_policy.py`, `injection_scanner.py`, `ssrf.py` | **aprovado com ressalva** (heurísticas, ver N18/N19) | N18, N19 | `ssrf` e `file_policy` usam Rust se existir, com fallback Python |
| Guardrails | `security/signing.py` | **adaptado** (1 linha) | N25 | `cryptography` |
| Guardrails | `security/scanner.py`, `capabilities.py`, `rate_limiter.py` | **adaptado (portar)** | N16 | **Rust obrigatório**; padrões Python existem só como dado morto |
| Guardrails | `security/boundary.py`, `guardrails.py` | **adaptado** | N16, N17 | dependem de `scanner.py` |
| Engine OpenAI-compat | `engine/_openai_compat.py`, `_base.py`, `_stubs.py`, `_http_async.py` | **aprovado** | N24 (menor) | `engine/__init__.py` importa ollama, nim, `_discovery` (que lê arquivo de mineração): **copiar os 4 arquivos para pacote próprio**, sem o `__init__` |
| Canal Telegram | `channels/telegram.py`, `_stubs.py` | **adaptado** | N22 | `python-telegram-bot`, `httpx` |
| Núcleo | `core/events.py`, `registry.py`, `types.py` | **aprovado** | nenhum | `core/__init__.py` importa `core.utils` (só `subprocess`/`webbrowser`, sem dependência externa) |
| Traces | `traces/collector.py`, `store.py` | **adaptado** | N23 | SQLite |
| Skills empacotadas | `skills/data/*.toml` | **adaptado** | N9 | — |

`aprovado` aqui significa: li o arquivo inteiro, não achei rede/execução/escrita fora do esperado nem defeito que mude o comportamento. Não significa ausência de bugs.

## 3. Achados novos

Severidade: **A** alta, **M** média, **B** baixa. "Só se" indica quando o risco depende de como você usa.

### Ferramentas e agentes

**N12 (M) — `ToolExecutor`: as defesas são opcionais e várias nascem desligadas.** `tools/_stubs.py`
- RBAC só roda se `capability_policy` não for `None` (`:331-337`), e o padrão do `CapabilityPolicy` é **liberar tudo** (`security/capabilities.py:54-57`). `ToolUsingAgent` passa `None` por padrão (`agents/_stubs.py:443-451`).
- `boundary_guard` existe (`:203`, `:306`) mas **nenhum agente o passa** (grep em `agents/*.py` sem resultado) e só vale para ferramentas com `is_local=False`.
- Taint e scanner de injeção iniciam em `try/except` e viram `None` em silêncio (`:220-234`).
- O cerco de injeção só vale para ferramentas com `is_local=False` (`:495-500`), mas o padrão da `BaseTool` é `True` (`:148`). Ferramentas MCP e `SkillTool` herdam `True`.
- Timeout não mata a thread (`:437-464`): o `shell_exec` pede 60 s no `spec` mas aceita até 300 s por dentro (`tools/shell_exec.py:18,74,96`), e o comando segue rodando. São só 8 workers (`:26`); se 8 ficarem presos, o executor devolve "capacity exhausted" (`:439-447`).
- O `TOOL_CALL_START` publica os argumentos completos no barramento (`:424-432`) e o `TOOL_CALL_END` publica 10 KB do resultado (`:530`); o coletor de traces grava tudo (N23).
- Bom: confirmação falha fechada. Ferramenta com `requires_confirmation` sem callback interativo **não executa** (`:401-411`).
- **Correção:** construir o executor sempre com `capability_policy` com `default_deny=True`, `boundary_guard` real, e `is_local=False` explícito em MCP/skills/web. Rejeitar nomes de ferramenta duplicados ao montar `_tools` (`:206`).

**N13 (M, funcional) — `LoopGuard` em Python bloqueia qualquer ferramenta chamada mais de 5 vezes.** `agents/loop_guard.py:111-120` aplica `poll_tool_budget=5` a **todas** as ferramentas, mas o docstring (`:40`) diz que só ferramentas de polling têm orçamento. Com `max_turns` de 10, a 6ª chamada de `web_search` na mesma execução é bloqueada. O caminho Rust pode se comportar diferente (não li o Rust). **Correção:** contar só ferramentas marcadas `spec.metadata["polling"]`.

**N14 (B) — acoplamento com `load_config`.** `BaseAgent.__init__` (`agents/_stubs.py:93-119`) e `ToolUsingAgent` (`:456-460`) leem `~/.openjarvis/config.toml` via `load_config()`, que importa `core/config.py` inteiro (2000+ linhas, todos os módulos). **Correção:** passar `temperature`, `max_tokens` e `max_turns` sempre (o `if` em `:93` evita o `load_config`).

**N15 (M, design) — observação de ferramenta entra como mensagem do usuário, sem delimitador.** `agents/native_react.py:348,355` empacota `Observation: {conteúdo}` com papel `USER`. Resultado de página web ou arquivo passa a ter a mesma autoridade do usuário. O único freio é N12 (cerco só para `is_local=False` e só para ocorrências "high/critical" de regex em inglês). **Correção:** envolver toda observação em delimitador e dizer ao modelo no prompt do sistema que o conteúdo é dado. Detalhe menor: `prompt_template.format(...)` (`:251`) formata um arquivo local de override com `str.format`, que permite `{tool_descriptions.__class__}`; só é problema se alguém externo escrever em `~/.openjarvis/agents/`.

**N19 (A, só se `allowed_dirs` vazio) — `file_read` irrestrito por padrão e a política de arquivos sensíveis não protege o próprio diretório do projeto.**
- `allowed_dirs` vazio = sem restrição (`core/config.py:1454-1455`; `tools/_paths.py:28-38`; `tools/file_read.py:53-55`).
- Padrões sensíveis: `security/file_policy.py:8-34`. **Não cobrem** `~/.openjarvis/config.toml` (guarda `bot_token` e chaves), `~/.openjarvis/connectors/*.json` (tokens OAuth), `~/.openjarvis/.vault_key` (`core/config.py:1456-1458`; `*.key` não casa com `.vault_key`), `id_ecdsa`, `.ssh/*`, `.aws/*`.
- O match é case-sensitive no Linux (`fnmatch`): `.ENV` passa.
- O tamanho é checado e depois o arquivo é lido de novo pelo Rust (`file_read.py:117-120`): janela de troca de arquivo (baixo).
- **Correção:** `allowed_dirs` obrigatório; incluir os padrões acima.

### Skills

**N1 (A para skills externas / B para as suas) — assinatura de skill é decorativa.**
- `skills/loader.py:109`: `if verify_signature and public_key and manifest.signature:` — se a skill **não tiver assinatura** ou você não passar chave, a verificação é **pulada sem erro**, mesmo com `verify_signature=True`.
- A assinatura cobre `manifest_bytes()` (`skills/types.py:37-59`): nome, versão, descrição, autor, passos, capabilities, tags, depends. **Não cobre** `markdown_content` (o corpo do SKILL.md, que é o que vira instrução para o modelo), `metadata`, `user_invocable`, `disable_model_invocation`.
- O caminho de descoberta nunca verifica: `discover_skills` → `load_skill(toml_file)` (`:283`) e `load_skill_directory` → `load_skill(toml_path)` (`:227`), ambos sem `verify_signature`. `SkillManager.discover` usa isso.
- `scan_for_injection` (`:125-141`) usa `SecretScanner` (detector de segredos, não de injeção), cai em `except ImportError: pass`, e **não olha o corpo do SKILL.md**.
- **Correção:** falhar fechado (`verify_signature` exige assinatura e chave); assinar também o corpo e `metadata`; usar `InjectionScanner` sobre o corpo.

**N2 (M) — injeção de argumento por substituição de template.** `skills/executor.py:206-216` troca `{chave}` por texto cru dentro de um JSON (`:109`, `:129`). Se o valor tiver aspas ou vírgulas, ele fecha o campo e acrescenta outros. Valores vêm de parâmetros do modelo **e da saída de passos anteriores** (`:139-140`: `ctx[output_key] = result.content`), ou seja, de páginas web e arquivos. **Correção:** montar o argumento com `json.dumps` por campo (substituir só dentro de strings já escapadas).

**N3 (M, só se importar skills externas) — o corpo do SKILL.md volta como observação "local" e o prompt manda obedecer.** `skills/tool_adapter.py:183-184` anexa `markdown_content` ao resultado; `SkillTool` herda `is_local=True` (sem cerco, `tools/_stubs.py:495-500`); e o prompt do ReAct instrui "READ the instructions carefully — they are your playbook / FOLLOW the steps" (`native_react.py:44-52`). Uma skill de terceiros é, na prática, injeção de prompt com a autoridade do agente.

**N4 (M) — não há imposição de capacidade para skills.** `SkillExecutor(...)` é criado sem `allowed_capabilities` nos três pontos do gerenciador (`skills/manager.py:199,214,385`); sem esse argumento, "todo skill roda" (`executor.py:46-50`). A faixa de confiança (`TrustTier`) só é usada na importação (`importer.py:123-139`), e lá o teste é sobre `required_capabilities` **declaradas pela própria skill** (`parser.py` aceita `required_capabilities` do frontmatter): uma skill maliciosa simplesmente não declara. O `sandbox_dangerous = True` (`core/config.py:1722`) **não é lido por nenhum código**. `SkillTool.spec` expõe as capacidades declaradas (`tool_adapter.py:133`) e o `ToolExecutor` ainda aplica as das ferramentas reais por passo (isso protege, se N12 for corrigido).

**N5 (A, prático) — `import yaml` sem dependência declarada.** `skills/loader.py:8`, `importer.py:25`, `sources/*.py`. `pyproject.toml:30-45` não lista PyYAML; ele só chega por `datasets`, `huggingface-hub`, `transformers` etc. (conferido no `uv.lock`). **Se você tirar `datasets` do núcleo, `import openjarvis.skills` quebra.** Como `skills/__init__.py:11` importa o importador, até as skills em TOML quebram. **Correção:** declarar `pyyaml` explicitamente.

**N6 (B) — profundidade de dependência derruba o `discover()`.** `skills/manager.py:116` só captura `DependencyCycleError`; `dependency.py:137` lança `DepthExceededError` (cadeia > 5), que sobe e aborta a descoberta inteira.

**N7 (B)** — `skills/index.py:24,66`: o `sha256` do índice é carregado e **nunca verificado** (grep em `skills/`).

**N8 (B)** — `skills/tool_translator.py:21-32` traduz para ferramentas que **não existem** neste código (`file_edit`, `file_glob`, `file_grep`, `delegate_agent`, `notebook_edit`); `WebFetch` vira `web_search`. Lista das ferramentas registradas: `grep ToolRegistry.register`.

**N9 (B/M) — skill empacotada `backup-files` provavelmente não funciona e interpola shell.** `skills/data/backup-files.toml`: o passo 1 guarda a saída de `shell_exec` em `timestamp`, mas a saída vem formatada com cabeçalhos (`tools/shell_exec.py:221-227`: `=== STDOUT ===\n...`, ou `Exit code:...` no Rust); o passo 2 monta `tar czf {destination}/backup_{timestamp}.tar.gz -C {source} .` sem aspas. Conclusão de leitura de código, não de execução. Quanto aos riscos: depende da confirmação do `shell_exec` (que é fail-closed) e de N2.

### Scheduler

**N10 (M) — falhas pequenas, efeitos largos.** `scheduler/scheduler.py`
- Todas as tarefas vencidas rodam em série na thread de polling (`:198-200`). Uma tarefa lenta atrasa todas; `self._system.ask(...)` não tem timeout (`:238-241`).
- Uma exceção em `_execute_task` (por exemplo, fuso inválido gravado no banco) aborta o `for` e as demais tarefas do ciclo (`:194-202`), e como `next_run` não avançou, a tarefa tenta rodar a cada ciclo.
- `ZoneInfo(...)` (`:329`) no Windows exige o pacote `tzdata`; ele só vem via `pandas` → `datasets` (`uv.lock`). Sem `datasets`, cron com `metadata.timezone` falha no Windows. **Correção:** declarar `tzdata` (marcador `sys_platform == 'win32'`).
- Entrega "pelo menos uma vez": se o processo cai no meio, a tarefa reexecuta. Sem `max_instances`.

**N11 (M-A) — o modelo pode se agendar.** `scheduler/tools.py:14-66`: `schedule_task` não tem `requires_confirmation` e aceita `prompt`, `agent` e `tools` vindos do modelo (`:90-93`). Um prompt injetado cria uma execução recorrente persistente, que roda depois sem você presente. A única barreira é a capability `schedule:create` (`capabilities.py:273`), e só vale com N12 corrigido. **Correção:** confirmação obrigatória, lista de ferramentas permitidas por tarefa e limite de tarefas.

### Memória

**N21 (M) — envenenamento de memória.** `memory/service.py:212-243`: o extrator recebe a troca inteira, **incluindo a resposta do assistente** (que pode refletir conteúdo web). Fatos que passam no scanner por regex entram como `TRUST_AUTO`, recuperáveis (`store.py:80-89`) e voltam em prompts futuros. O scanner **falha aberto** (`service.py:169-189`). Cada turno gera uma segunda chamada ao modelo com a conversa inteira (custo duplo; se o engine for nuvem, segundo envio do texto). Desligado por padrão (`core/config.py:973`, `enabled: bool = False`). **Correção:** só extrair do texto do usuário; fatos novos começam como `untrusted` até você aprovar.

### MCP

**N20 (M)**
- `mcp/transport.py:97-103`: `Popen(self._command, …)` sem `env=` → o servidor MCP herda **todas** as variáveis de ambiente (chaves incluídas). Sem `cwd`.
- `tools/mcp_adapter.py:36-54` e `mcp/client.py:110-116`: ferramentas remotas entram com `timeout_seconds=600`, sem confirmação, sem capabilities declaradas e com `is_local=True` (sem cerco, N12). A descrição e o nome vêm do servidor e entram no prompt.
- Colisão de nomes: o `ToolExecutor` guarda ferramentas num dicionário por nome (`tools/_stubs.py:206`); uma ferramenta MCP chamada `shell_exec` pode substituir a nativa e perder a confirmação. A defesa de capacidade cobre o caso (`capabilities.py:302-306` devolve `tool:invoke` por procedência), mas a confirmação some. `mcp/loader.py:129-136` aceita `include_tools`/`exclude_tools` só por configuração.
- Windows: `Popen([command] + args)` sem shell não resolve `npx.cmd` por padrão (comportamento conhecido do `subprocess`; não testado aqui).
- Bom: `StreamableHTTPTransport` não segue redirecionamentos (padrão do `httpx`), esconde o caminho da URL nas mensagens (`:289-294`), lê SSE (`:349-370`); o `StdioTransport` tem fila limitada, timeout total e leitura de stderr (`:61-256`).

### Segurança (peças reaproveitáveis)

**N16 (M) — scanners e capacidades só funcionam com Rust.**
- `security/scanner.py:22-23,97-99`: `SecretScanner()` e `PIIScanner()` chamam `get_rust_module()` no construtor. Os dicionários `PATTERNS` (`:25-76`, `:101-137`) são dados mortos: o `scan` vai sempre ao Rust (`:78-84`).
- `security/capabilities.py:68-71` (`CapabilityPolicy`) e `security/rate_limiter.py:70-76` (`RateLimiter`) também exigem Rust. A versão Python da checagem existe mas é "legado" (`capabilities.py:116-138`) e tem semântica diferente da usada em produção.
- `security/boundary.py:59-72`: sem Rust, `BoundaryGuard` fica **com zero scanners** e deixa tudo passar, só com um aviso no log.
- **Para o seu caso (sem Rust):** portar `PATTERNS` para um scanner Python (os regex já estão lá), reativar `_check_python` com testes e escrever `RateLimiter` Python (o `TokenBucket` já existe em `rate_limiter.py:22-56`).

**N17 (M) — guardrails não valem para respostas em streaming.** `security/guardrails.py:226-269` e `:271-315`: os tokens são entregues (`yield`) antes de qualquer varredura; a varredura de saída é "post-hoc, só para log". Modos `redact` e `block` não se aplicam à saída em streaming. Existem duas classes `SecurityBlockError` diferentes (`boundary.py:23`, `guardrails.py:16`). No modo `redact` a entrada do usuário também é alterada (e-mails, números).

**N18 (B-M) — heurísticas feitas para inglês/EUA.**
- `security/injection_scanner.py:26-106`: padrões em inglês ("ignore previous instructions"); em português passam. É um alarme, não uma barreira.
- `security/taint.py:62-77`: PII = SSN, cartão, telefone dos EUA, e-mail; não cobre CPF/CNPJ/telefone +55. O padrão genérico de segredo (`:73-76`: `(bearer|token|password|secret|key)\s*[=:]\s*\S{8,}`, sem distinção de caixa) casa com texto comum. O taint é cumulativo na sessão e semeado com **toda a conversa** (`agents/_stubs.py:476-484,501-507`; `tools/_stubs.py:365-394`): depois de um e-mail ou número de 10 dígitos aparecer, `web_search`/`http_request` passam a ser bloqueados naquele run (`taint.py:49-59`).

**N25 (B)** — `security/signing.py:119` grava a chave privada com `write_text` (permissão padrão do sistema, por exemplo 0644) apesar de existir `security/file_utils.py` com escrita 0600. Só afeta quem gera chaves.

**N26 (B)** — `security/audit.py:269-276` mapeia SECURITY_SCAN/ALERT/BLOCK todos para `SECRET_DETECTED`; o log de auditoria não distingue injeção, bloqueio ou segredo.

### Traces e eventos

**N23 (M)** — `traces/collector.py`: assina o barramento global e guarda estado em atributos da instância (`:55`, `:185`). Execuções simultâneas (servidor, scheduler, Telegram) misturam passos de um agente no trace de outro, porque os handlers não filtram por agente. Grava consulta, resposta, mensagens e argumentos/resultados de ferramentas em `traces.db` sem redação, e `traces.enabled=True` é o padrão (`core/config.py:1237`). Combinado com C1, o traço guarda a chave que foi expandida no cabeçalho.

**N27 (B)** — `core/events.py:153-163`: assinantes rodam de forma síncrona na thread que publica; um assinante lento (SQLite de trace/auditoria) trava o agente.

### Engine e Telegram

**N24 (B)** — `engine/_openai_compat.py:105-108`: em HTTP 400 com `tools`, repete a chamada **sem** `tools` e `tool_choice` em silêncio (o ReAct textual não depende disso). `:131-151`: um 200 com corpo inesperado levanta `KeyError`/`JSONDecodeError` não tratados. Sem retry/backoff para 429/5xx. Bom: o host vem do argumento ou de `<ID>_HOST`/`<ID>_API_KEY` (`:53-59`); nome de modelo passa direto (só `mlx` é reescrito, `model_catalog.py:1193-1204`); não há chamada a terceiros. Para o seu gateway basta registrar uma classe em `openai_compat_engines.py:21-27` ou instanciar `_OpenAICompatibleEngine(host=…, api_key=…)`.

**N22 (A para você) — Telegram aceita qualquer pessoa por padrão.** `channels/telegram.py`
- A lista de permissão é opcional: se `allowed_chat_ids` for vazio, **todas** as mensagens passam (`:398-409`).
- Mesmo preenchida, compara o **id do chat**, não o do usuário: qualquer membro de um grupo permitido fala com o agente.
- `handler(cm)` é chamado de forma síncrona dentro do callback assíncrono (`:410-414`): uma resposta lenta do modelo trava o bot inteiro. O valor de retorno do handler (`ChannelHandler -> Optional[str]`, `_stubs.py:34`) é ignorado; o handler precisa chamar `send` sozinho.
- `drop_pending_updates=True` (`:345`): mensagens recebidas enquanto o bot estava fora são descartadas.
- O token fica na URL (`:169`); falhas de rede são logadas com `exc_info` em nível debug (`:228`).
- **Correção:** lista de permissão obrigatória por **user id**; executar o agente fora do loop do PTB; falhar se a lista vier vazia.

## 4. O que está bem feito (útil para decidir)

- `ToolExecutor`: pool limitado de threads daemon, backpressure, confirmação que falha fechada, piso de capacidades por procedência (`capabilities.py:288-335`, inclusive o caso MCP), fila de eventos que não propaga erro de assinante.
- `memory/store.py`: escrita atômica, lock entre processos com versão para Windows, quarentena de fatos, tier de confiança, teto de fatos.
- `security/ssrf.py`: cobre IPv4 disfarçado, IPv6 mapeado, falha de DNS bloqueia. O Rust (`ssrf.rs`) usa o parser `url`, que normaliza essas formas. Limite: resolve o DNS antes e o cliente resolve de novo (sem fixar IP).
- `security/file_policy.py`: segue cadeia de symlinks e resolve o caminho final.
- `engine/*`: pequeno, sem efeito colateral, timeouts, tratamento de contexto estourado.
- `mcp/transport.py`: robusto contra ruído no stdout e deadlock de stderr.
- `scheduler`: fuso horário e persistência corretos para cron; a lógica de próxima execução está certa para `once`/`interval`/`cron`.

## 5. Receita mínima para o "Nó Único"

1. **Copiar sem mudanças:** `core/events.py`, `core/registry.py`, `core/types.py`, `memory/store.py` (e `core/paths.py`, só importa `os` e `pathlib`).
2. **Copiar e corrigir:** `agents/native_react.py` + `_stubs.py` (N14, N15), `agents/loop_guard.py` (N13, remover Rust), `tools/_stubs.py` (N12), `skills/{parser,types,executor,tool_adapter,manager,dependency,security}.py` (N1, N2, N4, N5, N6), `scheduler/{scheduler,store}.py` (+ `tools.py`) (N10, N11), `mcp/{client,transport,loader}.py` + `tools/mcp_adapter.py` (N20), `security/{taint,file_policy,injection_scanner,ssrf,signing}.py` (N18, N19, N25), `engine/{_openai_compat,_base,_stubs,_http_async}.py` num pacote próprio, `channels/{telegram,_stubs}.py` (N22).
3. **Escrever em Python:** scanner de segredos/PII (usar os regex de `scanner.py:25-76,101-137` e adicionar CPF/CNPJ), `CapabilityPolicy` (reativar `_check_python` com testes e `default_deny=True`), `RateLimiter` (usar o `TokenBucket`).
4. **Não levar:** `analytics`, `mining`, `evals`, `learning`, `connectors`, `speech`, `cli`, `server`, `agents/{executor,manager}.py`, `skills/{importer,index,sources}`, `tools/{shell_exec,repl,http_request}.py` como estão (reescrever com os patches C1-C4), `traces/` até resolver N23, `memory/{service,extractor}.py` até resolver N21.
5. **Dependências mínimas reais:** `httpx`, `openai` (opcional), `pyyaml`, `croniter`, `tzdata` (Windows), `python-telegram-bot`, `cryptography` (só se for verificar assinatura), `fastapi`/`uvicorn` (só se expor API).
