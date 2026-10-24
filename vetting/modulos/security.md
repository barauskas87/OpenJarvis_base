# security — ADAPTADO
Cobertura: [P] `ssrf.py` (quase inteiro), `subprocess_sandbox.py` (trechos), grep nos demais (20 arquivos).
- **Útil:** `scanner`/`injection_scanner` (segredos/prompt injection), `ssrf.py` (bloqueia IP privado, metadata, IPv4 disfarçado, IPv6 mapeado; DNS que falha = bloqueado, `OPENJARVIS_SSRF_FAIL_OPEN` desliga, `:146-156`), `capabilities`, `file_policy`, `rate_limiter`, `signing.py` (Ed25519 via `cryptography`), `data_boundary_audit.py` (auditor de config; cita Firecrawl e `skills.auto_sync` `:1572`).
- **Limitação do SSRF:** valida a resolução DNS antes do pedido e o cliente HTTP resolve de novo (janela de DNS rebinding); sem pinning de IP.
- **Rust:** `scanner.py:7`, `ssrf.py`, `file_policy.py`, `capabilities.py`, `rate_limiter.py`, `injection_scanner.py` importam `_rust_bridge`; `ssrf` tem fallback Python (`_rust_bridge.py` `RUST_AVAILABLE`), os demais exigem Rust.
- **Problema:** `subprocess_sandbox.py:96-105` `Popen(shell=True, preexec_fn=os.setsid)` → quebra no Windows; env limpo (`:14-60`).
- **Veredito:** adaptado: portar scanner/ssrf/capabilities para Python puro ou compilar Rust.
