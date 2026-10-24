# telemetry (local) — ADAPTADO/dispensável
19 arquivos [P]. SQLite local `telemetry.db` (`core/config.py` TelemetryConfig). Não envia nada externo; `vllm_metrics.py:134` lê `/metrics` do próprio vLLM; `energy_apple.py:98` chama subprocess. Não confundir com `analytics`. `system/builder.py:150-203` liga se `telemetry.enabled`.
