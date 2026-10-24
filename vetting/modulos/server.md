# server — ADAPTADO (reescrever a parte necessária)
Cobertura: [P] `app.py` (trechos 255-290, 435-520), `analytics_routes.py` inteiro; `auth_middleware.py` por grep; resto [V] (26 arquivos).
- `check_bind_safety` (`auth_middleware.py:104`) recusa bind não-loopback sem chave de API. `cli/serve.py:692-706` lê `OPENJARVIS_API_KEY` ou `[server.auth]`.
- CORS: origens por env `OPENJARVIS_CORS_ORIGINS` e padrão localhost; `"*"` é filtrado (`app.py:282-283`) mas `allow_credentials=True` (`:516`).
- Rotas que falam com terceiros: `agent_manager_routes.py` (Sendblue), `webhook_routes.py` (Twilio, WhatsApp), `cloud_router.py` (OpenAI, Anthropic, Google, OpenRouter…), `comparison.py` (página HTML), `analytics_routes.py`.
- Veredito: adaptado; copiar só `auth_middleware` e a ideia de `routes.py` OpenAI-compatível.
