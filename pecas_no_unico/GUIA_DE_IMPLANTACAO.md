# GUIA DE IMPLANTAÇÃO

- Python 3.10, 3.11, 3.12 e 3.13 testados no CI (Linux e Windows), todos verdes.
- No Windows, 33 testes são pulados de propósito (shell POSIX, symlinks, permissões 0600).
  Logo `shell_exec`, `_matar_arvore` e o transporte MCP stdio **não foram exercitados no Windows**.
- Chave de assinatura de skills: gravada com permissão 0600; guarde fora do repositório.
- Token do Telegram só por variável de ambiente; nunca em arquivo versionado.
- Estado em `get_config_dir()` é tratado como sensível (a ferramenta de leitura de arquivos o bloqueia).
- Checklist antes de subir: `ruff check src Tests`, `ruff format --check src Tests`, `python -m pytest`.

## Limitações conhecidas
- SSRF: há janela de DNS-rebinding entre a checagem e a conexão (mitigar com resolução fixada no transporte).
- Ferramenta que estoura o timeout continua rodando em thread (Python não mata threads); o processo filho do
  `shell_exec` é morto, outras ferramentas não.
- Agendador: entrega "no máximo uma vez" (tarefa reivindicada antes de rodar; queda no meio perde a execução).
- Canal Telegram: laço de polling real não foi testado sem o `python-telegram-bot` instalado.
