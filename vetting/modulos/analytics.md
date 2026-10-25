# analytics — REJEITADO
Cobertura: [L] `client.py`, `identity.py` lidos inteiros; `redaction.py` (80 linhas), `bridge.py`/`aggregator.py` por grep.
- **O que faz:** envia eventos de uso ao PostHog do projeto.
- **Rede:** `Posthog(project_api_key=…, host=…)` em `analytics/client.py:55-66`; `capture` em `:100-104`. Host/chave padrão em `core/config.py:1226-1227` (`https://34.231.106.201.sslip.io`, chave `phc_…` — valor omitido aqui). `disable_geoip=True` (`client.py:65`).
- **Padrão desligado:** `enabled: bool = False` (`core/config.py:1224`); `is_analytics_enabled` só devolve `cfg.enabled` (`identity.py:47-49`). Sem consentimento nada é enviado. Consentimento só em TTY (`cli/_analytics_consent.py:12-15`).
- **Disco:** `anon_id` UUID em `~/.openjarvis/anon_id` (`identity.py:31-36`) — só criado se habilitado (`client.py:41-45`).
- **Rota que expõe chave/host:** `server/analytics_routes.py:54-71` (devolve `key` só se habilitado).
- **Ligado no boot:** `server/app.py:446-457` chama `configure_analytics`; sem opt-in retorna cedo (`analytics_routes.py:95-96`).
- **Como desligar:** já é padrão; garantir `[analytics] enabled=false` no config; ou não importar o módulo. `posthog` está no núcleo (`pyproject.toml:37`), mas só é importado em `client.py:53`.
- **Frontend:** `frontend/src/lib/analytics.ts:105-139` inicializa `posthog-js` só após `identity.enabled`.
- **Veredito:** rejeitado (não copiar; remover `posthog` das dependências e a chave do `AnalyticsConfig`).
