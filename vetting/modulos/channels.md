# channels — REJEITADO exceto Telegram (ADAPTADO)
Cobertura: [V] + hosts por grep (38 arquivos).
- Registra 30+ canais; `channels/__init__.py:49` importa todos por `importlib.import_module(f".{_mod}")` (lista fixa).
- Telegram: `https://api.telegram.org/bot` (`channels/telegram.py`), token `TELEGRAM_BOT_TOKEN`, `allowed_chat_ids` (`core/config.py` `TelegramChannelConfig`). Ler inteiro antes de copiar.
- WhatsApp Baileys: `npm install --production` (`whatsapp_baileys.py:124-133`) e `node` (`:163`).
- Slack/iMessage daemons usam `signal.SIGTERM` (`slack_daemon.py:141`).
