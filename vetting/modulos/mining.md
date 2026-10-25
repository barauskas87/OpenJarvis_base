# mining — REJEITADO
Cobertura: [L] `_constants.py`, `_install.py`; [P] `_docker.py` (≈70% lido), grep em `_pearl_subprocess.py`, `cpu_pearl.py`, `apple_mps_pearl.py`, `_miner_loop_main.py`, `_mps_miner_loop_main.py`, `_discovery.py`, `cli/mine_cmd.py`, `cli/pearl_cmd.py`.
- **O que faz:** minerador de criptomoeda Pearl (PoW "NoisyGEMM") integrado a vLLM/CPU/Apple-MPS. É mineração real, declarada no código (`mining/__init__.py`, `_constants.py:1-8`).
- **Quando roda:** só por comandos `jarvis mine init|start|stop|…` (`cli/mine_cmd.py:386,522,537`). `cli/__init__.py:121,143` apenas registra o grupo. Nenhum agente/serve inicia mineração. `engine/_discovery.py:75-100` só lê `~/.openjarvis/runtime/mining.json` se existir.
- **Rede:** clone de `https://github.com/pearl-research-labs/pearl.git` (`_constants.py:14`) na ref `master` (`:17`, TODO no `:15-16`: sem commit fixo); `git fetch/checkout/submodule update --recursive` (`_docker.py` `_clone_pearl_repo`); RPC `http://localhost:44107` (`_constants.py:44`); HF (`cli/mine_cmd.py:118-131`).
- **Execução:** `docker buildx build` do código clonado após **patchear** Dockerfile e entrypoint (`_docker.py:172-249`); container com `network_mode="host"`, `restart_policy unless-stopped`, `shm_size 8g`, GPUs (`_docker.py:352-368`); subprocessos gateway+miner em CPU/MPS (`_pearl_subprocess.py:92,112`).
- **Segredos:** lê `PEARLD_RPC_PASSWORD` e `HF_TOKEN` do ambiente (`_docker.py:260,267,308-312`); redige em logs (`:31-33`).
- **Disco:** `~/.openjarvis/cache/pearl`, `runtime/mining.json` e `.lock` (`_constants.py:50-55`), logs.
- **Extras no pyproject:** `mining-pearl-vllm` (docker, httpx) e `mining-pearl-cpu` (vazio).
- **Veredito:** rejeitado. Risco: puxa código `master` mutável de terceiro e o compila/roda com GPU e rede de host. Não instalar nem copiar. Remover do CLI.
