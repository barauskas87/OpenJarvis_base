# sandbox — ADAPTADO
Cobertura: [P] `runner.py` linhas 1-200 de 733 linhas no módulo; `mount_security.py` não lido.
- `docker run --rm --network none -i` (`runner.py:113-124`), mounts `:ro` validados por allowlist (`:126-127`), segredos via stdin (`:169-174`), timeout 300 s (`:47`).
- Faltam: `--cap-drop=ALL`, `--security-opt no-new-privileges`, `--pids-limit`, `--memory`, `--read-only`, `--user`. Requer Docker/Podman no host.
