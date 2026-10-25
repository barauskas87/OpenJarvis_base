# core — ADAPTADO
Cobertura: [P] `config.py` (2000+ linhas; lidos trechos), `paths.py` (cabeçalho), `utils.py` (grep).
- Registry/eventos/tipos/paths úteis. `paths.py` resolve `OPENJARVIS_HOME` > `$XDG_DATA_HOME/openjarvis` > `~/.openjarvis` e recusa raiz dentro do código-fonte.
- `config.py:103` `_run_cmd` roda comandos de hardware (nvidia-smi etc.) com timeout 10 s; `:1901` `eval(fld_type, vars(_cfg_mod))` avalia só anotações de tipo do próprio módulo (benigno).
- `config.py:1211-1229` AnalyticsConfig com host/chave padrão (remover); `:1717` SkillsConfig `index_repo`.
- `utils.py:67,111,158,176`: `ps`, `cmd /c start`, `taskkill` (listas, sem shell).
