# skills — ADAPTADO
Cobertura: [P] `security.py`, `importer.py` (cabeçalho), `sources/base.py`, `loader.py` (trechos); resto [V].
- **O que faz:** carrega skills (TOML bundled em `skills/data/*.toml`, SKILL.md estilo agentskills.io), executa passos via `ToolExecutor` (`executor.py:131`), importa de fontes externas.
- **Trust tiers** `bundled > workspace > indexed > unreviewed` e capacidades perigosas `shell:execute, network:listen, filesystem:write` (`security.py:9-37`).
- **Rede/exec:** `sources/base.py:59-75` `git pull --ff-only`/`git clone` de repositórios de terceiros no cache; `hermes.py`/`openclaw.py` apontam para `NousResearch/hermes-agent` e `openclaw/skills`; índice padrão `https://github.com/openjarvis/skill-index.git` (`core/config.py:1717`; **organização `openjarvis`, diferente de `open-jarvis`** — verificar quem controla).
- **Scripts de skill:** pulados por padrão (`importer.py:8,149-201`, `with_scripts=False`).
- **`auto_sync` padrão false** (`config.py`/`data_boundary_audit.py:1572`); `scan_for_injection` padrão false (`loader.py:51`).
- **Veredito:** adaptado: manter parser/loader/executor/security/importer; remover `sources/` e `index_repo`; ligar `scan_for_injection`.
