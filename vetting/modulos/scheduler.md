# scheduler — ADAPTADO
Cobertura: [P] cabeçalho e trechos de `scheduler/scheduler.py` (864 linhas no módulo); `agents/scheduler.py` [V].
- Cron/interval/once com polling e SQLite (`scheduler.py:1-30,77-110`), usa `croniter` (obrigatório, `:321-324`), timezone configurável.
- Sem rede, sem subprocess. Persistência `scheduler.db` em `~/.openjarvis`.
- **Veredito:** adaptado: bom candidato; ler os 864 linhas completas antes de copiar.
