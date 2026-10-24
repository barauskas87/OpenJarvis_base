# Vetting OpenJarvis — Resumo (tarefa F1, somente leitura)

- **Commit analisado:** `0ec344454de38525f3cfc52a8e06012e18871a7b` (2026-10-24T06:15:36+00:00), branch base `main`.
- **Método:** nada foi executado, instalado, compilado ou importado. Só `cat/grep/find/file/sha256sum` e leitura de arquivos.
- **Licença:** Apache-2.0 (`pyproject.toml`).
- **Arquivos por pasta (git ls-files):** `src` 954 · `tests` 739 · `frontend` 136 · `rust` 146 · `docs` 99 · `examples` 43 · `.github` 23 · `scripts` 17 · `deploy` 14 · `configs` 12 · `assets` 4 · `desktop` 2 · raiz 11 arquivos.
- **Python em `src/openjarvis`:** ~190 mil linhas, 32 módulos (o maior é `evals`, 37 mil linhas, que é benchmark e não interessa).

## Resumo executivo

O código **não tem backdoor, mineração oculta, ofuscação nem segredo privado embutido**. Não achei base64/zlib/marshal escondendo código, nem `verify=False` em TLS, nem execução de binário baixado de host estranho. A telemetria existe, mas é **opt-in (desligada por padrão)**. A mineração (Pearl) existe de verdade, mas só roda se você digitar `jarvis mine init/start`.

Os problemas reais são outros: (1) o núcleo tem dependências e hosts que você não quer (posthog, datasets, ddgs, python-telegram-bot, nvidia-ml-py); (2) **o Rust é obrigatório** para várias ferramentas e para a camada de segurança, e no Windows exige MSVC; (3) as ferramentas de execução têm **furos de segurança** (abaixo); (4) o instalador de um comando faz `curl | sh` de 3 terceiros e clona `main` sem fixar versão.

**Recomendação geral:** NÃO instalar o pacote inteiro. Usar o OpenJarvis como **biblioteca de peças**, copiando (depois de patch) só: `agents/native_react.py` + `_stubs.py` + `loop_guard`, `tools/_stubs.py` (ToolExecutor), `skills/` (parser/loader/executor, sem `sources/`), `scheduler/`, `memory/store.py`, `mcp/` (cliente/servidor), `security/` (scanner, ssrf, capabilities). Excluir `analytics/`, `mining/`, `evals/`, `learning/`, `connectors/`, `channels/` (exceto Telegram, via cópia isolada), `server/` (reescrever sobre FastAPI próprio) e todo `deploy/`, `desktop/`, `frontend/`, `scripts/install`.

## Achados críticos

| # | Gravidade | Achado | Onde |
|---|---|---|---|
| C1 | Alta | `http_request`: `os.path.expandvars` aplicado aos cabeçalhos que o modelo escolhe. Um prompt malicioso pode pedir `Authorization: Bearer $OPENAI_API_KEY` para um host público e vazar chaves do ambiente. | `src/openjarvis/tools/http_request.py:112-114` (expandvars na linha 113) |
| C2 | Alta | Caminho Rust do `http_request` não segue a checagem de SSRF a cada redirecionamento: `reqwest` segue até 10 redirects por padrão e só a URL inicial passa por `check_ssrf`. Python trata redirects à mão (linha 140-143), Rust não. | `rust/crates/openjarvis-tools/src/builtin/http_tools.rs:45-52`; `http_request.py:149-153, 207` (redirects manuais só no caminho Python; o atalho Rust é nas linhas 118-136, usado quando não há cabeçalhos) |
| C3 | Alta | `shell_exec`: quando a extensão Rust existe, o código Python monta ambiente limpo e timeout (linhas 110-148) e **ignora tudo**: chama `_rust.ShellExecTool().execute(command, working_dir)`. O Rust roda `sh -c`/`cmd /C` herdando TODO o ambiente (chaves de API), sem timeout e sem limite de saída. | `src/openjarvis/tools/shell_exec.py:151-164`; `rust/.../builtin/shell.rs:43-57` |
| C4 | Alta | `repl` roda `exec/eval` **no mesmo processo** do servidor, protegido só por lista de substrings e builtins removidos. Escapável (ex.: `().__class__.__base__.__subclasses__()`, `__class__` não é bloqueado). | `src/openjarvis/tools/repl.py:21-45, 304-311`; idem `agents/rlm_repl.py:28-40, 218` |
| C5 | Média | Telemetria PostHog: chave `phc_…` e host `https://34.231.106.201.sslip.io` (IP cru, fora de domínio do projeto) embutidos como padrão. Desligada por padrão (`enabled=False`), mas o frontend também embute `posthog-js` e a rota `/v1/analytics/identity` entrega chave e host. | `core/config.py:1224-1227`; `analytics/client.py:51-66`; `scripts/install/install.sh:257-258`; `server/analytics_routes.py:54-71` |
| C6 | Média | Mineração real de criptomoeda (Pearl): clona `https://github.com/pearl-research-labs/pearl.git` na ref **`master`** (sem commit fixo, TODO no código), faz `docker buildx build` e roda container com `network_mode="host"`, `restart unless-stopped`, passando `HF_TOKEN`. Só por comando explícito `jarvis mine`. | `mining/_constants.py:14-17`; `mining/_docker.py:172-200, 362-370`; `cli/mine_cmd.py:386, 522` |
| C7 | Média | Instalador `install.sh` faz `curl … \| sh` de: astral.sh (uv), ollama.com, sh.rustup.rs; clona `main` sem hash; edita `~/.bashrc`/`~/.zshrc`; dispara processo em background que instala Rust e compila extensão. | `scripts/install/install.sh:534, 548-550, 642`; `install-rust.sh:14`; `install.sh:715-737` (ensure_path, escreve em rc na linha 735) |
| C8 | Média | Binário de 77 MB commitado: `desktop/src-tauri/binaries/ollama-aarch64-apple-darwin` (Mach-O universal x86_64+arm64, sha256 `6f632c7a…260b3a`). Não dá para auditar; não usar. | `desktop/src-tauri/binaries/` |
| C9 | Média | Fonte de skills de terceiros por `git clone/pull` sem fixar commit: `NousResearch/hermes-agent`, `openclaw/skills`, e um índice em **`github.com/openjarvis/skill-index.git` (organização diferente de `open-jarvis`)**. Scripts de skill são pulados por padrão (`with_scripts=False`), o que mitiga. | `skills/sources/base.py:59-75`; `hermes.py`/`openclaw.py`; `core/config.py:1717`; `skills/importer.py:149-201` |
| C10 | Baixa | Checagem de versão no PyPI ligada por padrão nos comandos ask/chat/serve/etc. (`urllib` para `pypi.org`). Desliga com `OPENJARVIS_NO_UPDATE_CHECK=1`, `CI=true` ou `[updates] auto_update=false`. | `cli/_version_check.py:18, 52-68, 98, 166-175` |
| C11 | Baixa | `subprocess_sandbox` usa `shell=True` e `preexec_fn=os.setsid` (quebra no Windows). | `security/subprocess_sandbox.py:99, 105` |
| C12 | Baixa | `curl \| sh` do Ollama embutido em `jarvis host` (com `shell`), e `npm install` automático em `whatsapp_baileys` e `claude_code`. | `cli/host_cmd.py:239`; `channels/whatsapp_baileys.py:124-133`; `agents/claude_code.py:149` |

## O que NÃO encontrei (honestamente, dentro da cobertura abaixo)

Mineração oculta (a mineração é opt-in e declarada), código ofuscado, `eval` de strings baixadas, `verify=False`/`CERT_NONE`, tokens privados (só a chave pública PostHog e a URL Supabase de leaderboard, que é pública por desenho; chaves em testes/docs são fictícias), escrita fora de `~/.openjarvis`, leitura de `~/.ssh`/cookies de navegador (não procurei cookies de navegador em `tools/browser.py` a fundo).

## Python e Windows

- `requires-python = ">=3.10,<3.14"` (`pyproject.toml:14`). Python 3.14 é rejeitado por falta de wheel do numpy no Windows.
- Windows nativo: existe `deploy/windows/install.ps1` (suporte "fase 1"), mas **exige MSVC Build Tools + compilar Rust** (`install.ps1` seção 5b/6). `install.sh` recusa Git Bash/MSYS e manda usar WSL2. Pontos que quebram no Windows: `security/subprocess_sandbox.py:105` (preexec_fn), `tools/code_interpreter.py:95-101` (módulo `resource`, tratado com try), `agents/hybrid/runner.py:21` (`import fcntl` sem guarda; é pesquisa, descartável). `memory/store.py:29` tem guarda correta para Windows.

## Cobertura (o que li de verdade)

Li **inteiros**: `analytics/client.py`, `identity.py`, `cli/_analytics_consent.py`, `server/analytics_routes.py`, `tools/shell_exec.py`, `rust/.../shell.rs`, `mining/_constants.py`, `mining/_install.py`, `scripts/install/*.sh` (os 7), `deploy/windows/install.ps1`, `deploy/posthog/posthog-hetzner-prep.sh`, `render.yaml`, `Makefile`, `pyproject.toml`, `deploy/systemd/openjarvis.service`, `deploy/docker/docker-compose.yml`.
Li **em parte** (trechos relevantes): `core/config.py`, `server/app.py`, `cli/serve.py`, `mining/_docker.py`, `sandbox/runner.py`, `tools/repl.py`, `tools/code_interpreter.py`, `tools/http_request.py`, `security/ssrf.py`, `security/subprocess_sandbox.py`, `skills/*` (security/importer/sources), `connectors/oauth.py`, `cli/_version_check.py`, `deploy/docker/Dockerfile` (60 linhas), `deploy/windows/jarvis-service.ps1` (150 linhas), `frontend/src/lib/analytics.ts`, `supabase.ts`, `frontend/src-tauri/src/lib.rs` (só grep).
**Não li linha a linha (só varredura por padrões `grep`, contagem por módulo e leitura de trechos):** `evals` (319 arquivos), `learning`, `connectors` (exceto oauth), `channels` (exceto menções), `cli` (exceto os citados), `server` (exceto app/analytics), `tools/storage`, `agents/hybrid`, `speech`, `telemetry`, `rust/` (exceto shell/http), `frontend/` (exceto 3 arquivos), `tests`, `docs`, `examples`, `configs`, `.github/workflows` (só grep de curl/secrets), `deploy/docker/Dockerfile.*`, `desktop/src-tauri/src/overlay.html`, `scripts/*.py` e `scripts/quickstart.sh` etc. Por isso **nenhum módulo grande recebe `aprovado` sem ressalva**; os vereditos são sobre o que li + padrões perigosos que busquei em todo o código. O `uv.lock` foi checado só por fontes (452 pacotes do PyPI, 1 editável, 1 diretório local `rust/crates/openjarvis-python`; nenhuma fonte git/url) e versões de alguns pacotes; **não** auditei cada pacote transitivo.
