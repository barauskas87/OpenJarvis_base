# agents — ver 02_matriz.md
Cobertura: [P] `native_react.py` (lido ~150 linhas), `loop_guard.py:55-80`, `rlm_repl.py:20-80`, `opencode.py:285-312`, `claude_code.py:140-200`; [V] resto (73 arquivos, 24 mil linhas).
- **Aproveitar:** `native_react.py` (ReAct JSON Thought/Action/Observation, parser tolerante `:74-130`), `_stubs.py` (`BaseAgent/ToolUsingAgent`), `loop_guard.py` (usa Rust se disponível, `:58-79`; verificar fallback), `prompt_loader`, `executor/manager`.
- **Rejeitar:** `rlm_repl.py` (exec em processo), `claude_code*`, `opencode.py` (env herdado `:293`), `openhands*`, `hybrid/*`.
- CodeAct: não achei agente CodeAct dedicado; `rlm`/`native_openhands` são os mais próximos.
