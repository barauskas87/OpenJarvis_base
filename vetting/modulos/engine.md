# engine — ADAPTADO
Cobertura: [P] (listagem, `openai_compat_engines.py` inteiro, trechos de `cloud.py`/`_discovery.py`).
- **O que faz:** clientes de inferência: Ollama, vLLM, SGLang, llama.cpp, MLX, LM Studio, exo, nexa, uzu, Apple FM, lemonade (`openai_compat_engines.py:8-19`, hosts padrão todos `localhost`), `cloud.py` (OpenAI, OpenRouter `:463`, AtlasCloud `:474`, MiniMax `:485`, DeepSeek `:496`), `nim.py` (integrate.api.nvidia.com), `litellm.py`.
- **Rede:** só para o host configurado; nuvem apenas se escolher engine `cloud`. Sem chamadas ocultas.
- **Gateway OpenAI:** `_OpenAICompatibleEngine` (`_openai_compat.py`) + `OPENAI_BASE_URL` (comentário `cloud.py:219`) atendem seu caso sem mudança de lógica.
- **Env:** `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OLLAMA_HOST` (20 leituras).
- **Mudança exigida:** podar engines extras; `__init__.py:33` importa opcionais dinamicamente (`importlib.import_module`, nomes fixos — ok); remover registro por sidecar de mineração (`_discovery.py:75-100`).
- **Veredito:** adaptado.
