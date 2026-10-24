# tools — ADAPTADO (com 3 correções obrigatórias; repl rejeitado)
Cobertura: [L] `shell_exec.py`, `shell.rs`; [P] `repl.py`, `code_interpreter.py`, `http_request.py`, `docker_shell_exec.py`; [V] o resto (68 arquivos).
## shell_exec (C3)
- `tools/shell_exec.py:110-148` monta timeout e ambiente mínimo (`PATH,HOME,USER,LANG,TERM`).
- `:151-164` se `openjarvis_rust` importa, chama `_rust.ShellExecTool().execute(command, working_dir)` e **retorna**, sem usar `env`/`timeout`.
- `rust/crates/openjarvis-tools/src/builtin/shell.rs:43-57`: `sh -c`/`cmd /C`, `cmd.output()` sem `env_clear`, sem timeout, sem limite de saída. Binding Python: `openjarvis-python/src/tools.rs:126-137`.
- Ramo Python: `subprocess.run(shell=True)` (`:179-188`), `requires_confirmation=True` (`:95`) e capability `code:execute` (`:97`); a confirmação depende do `ToolExecutor` (`_stubs.py` ~ `confirm_callback`).
- Correção: apagar `:151-166`; sempre `env=env`.
## http_request (C1, C2)
- `http_request.py:112-114`: `os.path.expandvars(v)` nos cabeçalhos fornecidos pelo agente → exfiltra `$OPENAI_API_KEY` etc.
- Com Rust e sem cabeçalhos (`:118-136`) usa `http_tools.rs:49-52`, `reqwest::blocking::Client` com política padrão (segue 10 redirects). SSRF é checado só na URL inicial (`:45`). O caminho Python segue redirects manualmente (`:149-153`, `:207`).
## repl (C4)
- `tools/repl.py:21-32` blocklist de substrings; `:35-46` builtins removidos; `:304-311` `eval/exec` no namespace da sessão, no mesmo processo. `__class__`/`__subclasses__` não bloqueados. Veredito: rejeitado. (O próprio projeto comenta o problema em `tools/templates/loader.py:25-35`, que usa um interpretador AST e não `eval`.)
## code_interpreter
- Validação AST com allowlist `{json,math,time}` (`code_interpreter.py:~28`), processo filho `-I -B -S`, rlimits (`:94-120`), ambiente limpo. Documenta que "é filtro, não jaula" (docstring `:7-16`). Uso seguro só dentro de Docker (`code_interpreter_docker.py`).
## Rede de outras tools
`web_search.py` (Firecrawl, Serply, You.com, DDG, Tavily), `weather.py` (OpenWeather), `fx_macro.py` (`api.fxmacrodata.com`), `browser.py` (Playwright). Todas dependem de chaves/entradas do usuário.
## Escrita
`file_write.py`, `apply_patch.py`, `storage/*` gravam em caminhos escolhidos pelo agente; checar `security/file_policy.py`.
