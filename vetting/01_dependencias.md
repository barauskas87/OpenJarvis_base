# 01 — Dependências (pyproject.toml e uv.lock)

Fonte: `pyproject.toml` (319 linhas) e `uv.lock` (454 pacotes: 452 do PyPI `https://pypi.org/simple`, 1 editável `.`, 1 diretório local `rust/crates/openjarvis-python`). Nenhuma fonte `git+` ou `url` no lock. Build: `hatchling` + `hatch-vcs` (versão vem de tag git; sem `.git` cai em `0.0.0+unknown`). Binário de console: `jarvis` e `openjarvis-eval`.

## Núcleo (`[project].dependencies`, `pyproject.toml:30-45`) — instalado SEMPRE

| Pacote | Faz o quê | Alerta |
|---|---|---|
| `click`, `rich`, `tomlkit`, `tomli` | CLI / TOML | ok |
| `httpx`, `openai` | HTTP e cliente OpenAI (serve para gateway compatível) | rede, esperado |
| `croniter` | cron do scheduler | ok |
| **`posthog`** | SDK de telemetria | **TELEMETRIA no núcleo.** Só é importado em `analytics/client.py:53` e só se `analytics.enabled=true`. Instalado mesmo assim. |
| **`datasets`** (>=4.5.0) | HuggingFace datasets | **Pesado** (puxa pyarrow, pandas, numpy, fsspec…); só os `evals` usam. Rede em tempo de execução para baixar datasets. Não precisa no núcleo. |
| **`ddgs`** | busca DuckDuckGo | **Rede** (scraping de busca). Só `tools/web_search.py`. |
| **`python-telegram-bot`** | canal Telegram | rede (api.telegram.org); útil para o Victor |
| **`nvidia-ml-py`** | leitura de GPU NVIDIA | acesso a sistema (driver); usado em telemetria/hardware |
| `psutil` | processos | acesso a sistema (usado pelo `jarvis gui`) |
| `websockets` | WebSocket | rede (canais/ws_bridge) |

Núcleo também exige a extensão Rust `openjarvis-rust` via `[tool.uv.sources]` (`pyproject.toml:243-244`), mas ela fica no grupo `desktop-native`, não na lista acima; mesmo assim o código faz `import openjarvis_rust` em várias ferramentas (`_rust_bridge.py:23-28`), ver 00_RESUMO.

## Extras (`[project.optional-dependencies]`)

| Extra | Pacotes | Observação |
|---|---|---|
| `dev` | maturin, pytest*, respx, ruff, pre-commit | só desenvolvimento |
| `inference-mlx` | `mlx-lm` (só macOS) | local |
| `inference-vllm` | `vllm>=0.30.0` | local, GPU, pesado |
| `inference-cloud` | openai, **anthropic** | rede para nuvem |
| `inference-google` | google-genai | rede |
| `inference-litellm` | `litellm==1.104.2` | **execução de código/rede**: o pin exato é por advisories de injeção de comando e do incidente de supply-chain de março (versões 1.82.7/1.82.8). Evitar. |
| `inference-gemma` | `pygemma` | pacote de baixa reputação; não revisado |
| `tools-search` | tavily-python, ddgs | rede |
| `memory-faiss` | faiss-cpu, sentence-transformers, numpy | baixa modelos do HF em tempo de execução |
| `memory-colbert` | colbert-ai, torch | pesado; baixa modelos |
| `memory-pdf`, `pdf` | pdfplumber | leitura de PDF |
| `memory-bm25` | rank-bm25 | local |
| `server` | fastapi, uvicorn, pydantic, python-multipart | **necessário** se usar servidor |
| `desktop` | server + faster-whisper, av, onnxruntime, numpy, sounddevice, soundfile | baixa modelo whisper do HF; acesso a microfone |
| `voice` | kokoro, soundfile, sounddevice, numpy | TTS local; baixa modelo; **kokoro_tts.py:76-98 troca `builtins.__import__` temporariamente** |
| `openhands` | `openhands-sdk` (py>=3.12) | agente que executa código; não revisado |
| `afm` | apple-fm-sdk (macOS) | compila Swift na instalação |
| `gpu-metrics` | pynvml | acesso a sistema |
| `energy-amd` | `amdsmi` | acesso a sistema (driver AMD) |
| `energy-apple` | `zeus-apple-silicon` (macOS) | acesso a IOReport (energia) |
| `energy-all` | pynvml + amdsmi + zeus-apple-silicon | só leitura de contadores de energia |
| `orchestrator-training` | torch, transformers | treino |
| `learning-dspy` | `dspy` | **executa prompts/otimizações via LLM; rede**; `dspy` instala `litellm` como transitivo |
| `learning-gepa` | `gepa` | idem; rede para LLM |
| `channel-telegram` | python-telegram-bot | **útil** |
| `channel-discord/slack/line/viber/messenger/reddit/mastodon/xmpp/rocketchat/zulip/twitter/twitch/nostr/twilio/gmail` | SDKs de cada serviço | **rede** com credenciais do usuário; `channel-twitter` só `httpx`; `channel-nostr` usa chave privada |
| `browser` | `playwright>=1.40` | **execução de navegador real** (`tools/browser.py`); baixa Chromium (`playwright install`, não automático no código). Acesso a páginas arbitrárias. |
| `media` | openai | rede |
| **`mining-pearl-vllm`** | `docker>=7.0`, `httpx` | **MINERAÇÃO**: SDK Docker (controle total do daemon). Use só com `jarvis mine`. |
| **`mining-pearl-cpu`** | *(vazio)* | extra vazio de propósito: os pacotes Pearl (`py-pearl-mining`, `miner-utils`, `pearl-gateway`, `miner-base`, `mining/_constants.py:36-41`) "serão instalados no primeiro `mine init` por build-from-pin" (comentário `pyproject.toml:190-196`). **Instalar este extra não faz nada hoje**, mas o código prevê baixar/compilar do repo `pearl-research-labs/pearl` (ref `master`). |
| `scheduler` | croniter | redundante (já no núcleo) |
| **`security-signing`** | `cryptography>=43` | assinatura de skills (`security/signing.py`); **sem rede**; seguro e útil |
| `sandbox-wasm` | `wasmtime>=25` | sandbox WASM; sem rede |
| `sandbox-docker` | `docker>=7.0` | controla Docker; o `sandbox/runner.py` usa `docker run --network none` |
| `dashboard` | textual | TUI |
| `speech` | faster-whisper, av, onnxruntime, numpy, sounddevice, soundfile | baixa modelo; microfone |
| `speech-deepgram` | deepgram-sdk | **envia áudio** para nuvem |
| `eval-wandb` | **wandb** | **telemetria/upload de resultados para W&B** (nuvem); só `evals` |
| `eval-sheets` | gspread, google-auth | Google Sheets |
| `framework-comparison` | polars | benchmark |
| `docs` | mkdocs* | documentação |

## Nota sobre `energy-*`, `learning-*`, `channel-*`, `sandbox-*`, `security-signing`, `browser`

- `energy-*`: só leem contadores de energia/GPU (`telemetry/`), sem rede. Risco baixo. `telemetry/energy_apple.py:98` chama um `subprocess` (ver módulo telemetry).
- `learning-*` / `orchestrator-training`: otimização/treino; gravam muito em disco em `~/.openjarvis` e chamam LLMs. Não são necessários para um agente local simples.
- `channel-*`: cada um conversa com um serviço externo. Fora Telegram, não precisa.
- `sandbox-*`: úteis para contenção; `sandbox-docker` é a única forma real de isolar `code_interpreter`.
- `security-signing`: benigno.
- `browser`: poderoso e perigoso (navegação aberta). Só com allowlist de domínios.

## Versões / Python

`requires-python = ">=3.10,<3.14"`. Dependências com restrição de plataforma: `mlx-lm` (darwin), `apple-fm-sdk` (darwin), `zeus-apple-silicon` (darwin), `onnxruntime<1.24` (py3.10 e Intel Mac), `openhands-sdk` (py>=3.12). Dependência de Rust: `rust-version` 1.88/1.89 (Dockerfile usa 1.88; commit "require Rust 1.89" no histórico).

## Pacotes do lock que merecem atenção (não auditados linha a linha)

`litellm 1.104.2` (pin deliberado por segurança), `lmnr` (observabilidade/telemetria, dependência de `openhands-sdk` em `uv.lock:5174-5183` — **telemetria de terceiros** se o extra `openhands` for instalado), `posthog`, `wandb`. Para o seu uso (gateway OpenAI), o conjunto mínimo seria: `click, rich, tomlkit, httpx, openai, croniter, python-telegram-bot` (+ `fastapi/uvicorn` se quiser servidor), **sem** posthog, datasets, ddgs, nvidia-ml-py, psutil.
