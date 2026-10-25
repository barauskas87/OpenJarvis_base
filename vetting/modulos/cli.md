# cli — REJEITADO (como módulo a copiar)
Cobertura: [P] grep + trechos (58 arquivos, 17.8 mil linhas).
- Rede: `_version_check.py:18,166-175` (PyPI, 3 s timeout, liga por padrão), `model.py:295-305` (`huggingface_hub.snapshot_download`), `tunnel_cmd.py:36` (cloudflared), `host_cmd.py:239` (`sh -c "curl -fsSL https://ollama.com/install.sh | sh"`, só após `click.confirm(..., default=True)` em `:235`), `self_update_cmd.py:29-82,154` (`git pull`, `uv sync`, `shlex.split(upgrade_command)`).
- Execução: `gui_cmd.py:445` `npm install`; `gateway_cmd.py` launchctl/systemctl.
- `init_cmd`/`_analytics_consent.py` perguntam telemetria (padrão não).
- Veredito: rejeitado; escrever CLI própria. Útil como referência: `serve.py`, `_bootstrap.py`, `doctor_cmd.py`.
