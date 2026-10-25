# mcp — ADAPTADO
Cobertura: [P] `server.py` cabeçalho, `transport.py:75-110`.
- Cliente MCP por stdio: `subprocess.Popen(self._command, …)` sem shell (`transport.py:97-103`) herdando o ambiente; comando vem do config.
- Servidor MCP expõe tools do OpenJarvis com anotações readOnly/destructive (`server.py` `_TOOL_ANNOTATIONS`).
- **Mudanças:** allowlist de comandos, `env` explícito, timeout.
