# connectors — REJEITADO
Cobertura: [P] `oauth.py` (trechos) e URLs por grep (41 arquivos).
- Integrações de dados pessoais: Gmail/IMAP, Drive, Calendar, Contacts, Notion, Slack, Dropbox, Spotify, Strava, Oura, Granola, Apple Notes/Health/Music/Messages, iMessage, WhatsApp.
- OAuth local em `127.0.0.1:8789` (`oauth.py` `callback_port`), tokens JSON em `~/.openjarvis/connectors/*.json` com permissão 0o600 (`oauth.py:261`). `apple_music.py` usa subprocess.
- Fora de escopo para o nó; risco de privacidade alto.
