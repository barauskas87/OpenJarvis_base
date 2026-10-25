# GUIA DE INTEGRAÇÃO

1. Copie `src/openjarvis/` para dentro do Nó Único (mantenha o nome do pacote) e `Tests/`, `pytest.ini`,
   `ruff.toml`, `requirements.txt` para a raiz.
2. `pip install -r requirements.txt`.
3. Rode os testes: `python -m pytest` (a partir da raiz).
4. Ordem sugerida de ligação:
   `security` → `tools/_stubs` (ToolExecutor) → ferramentas → `agents/native_react` → `skills` →
   `scheduler` → `mcp` → `channels`.
5. Pontos de atenção ao ligar:
   - `ToolExecutor` nega por padrão: registre uma `CapabilityPolicy` explícita (existe `permissiva()` só p/ testes).
   - MCP: informe `allowed_commands` e `allowed_hosts`; nada sobe sem estar na lista.
   - Agendador: informe quais agentes/ferramentas podem ser agendados.
   - Telegram: defina IDs autorizados; sem lista, ninguém é atendido. O handler que devolve `str`
     já é enviado como resposta — não envie de novo manualmente.
   - `build_memory_service` espera um objeto de configuração com os atributos usados (duck-typing).
6. Conferir diferenças com o upstream: `patches/*.patch` (50 arquivos, `diff -u`).
   Aplicar sobre um checkout do upstream: `patch -p1 < patches/<arquivo>.patch`.
