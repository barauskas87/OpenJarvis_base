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

## Alvos
Linux (servidor/desktop) e Android (app). Detalhes e restrições por plataforma em `PLATAFORMAS.md`.

## Servidor do Nó (Linux)
- Rode como usuário sem privilégios; porta acima de 1024; firewall liberando só a rede local/VPN.
- Exemplo de `systemd` (`/etc/systemd/system/no-unico.service`):
  ```
  [Service]
  User=nounico
  EnvironmentFile=/etc/no-unico/ambiente   # contém NO_UNICO_TOKEN_HASHES=...
  ExecStart=/opt/no-unico/venv/bin/python -m openjarvis.servidor servir --host 0.0.0.0 --porta 8443 \
            --certificado /etc/no-unico/certificado.pem --chave /etc/no-unico/chave.pem \
            --motor-host http://127.0.0.1:8000 --modelo NOME
  Restart=on-failure
  NoNewPrivileges=true
  ```
- `chave.pem` com permissão 0600 e dono `nounico`.
- Revogar um token = tirar o hash da lista e reiniciar. Trocar = gerar outro e atualizar o app.
- Certificado autoassinado vence (o gerado acima, em 365 dias): renove e cole o novo PEM no app.

## Limitações da API (versão 1)
- Sem streaming (resposta inteira de uma vez); sem notificações push.
- Histórico, limites de uso e contagem de falhas ficam na memória: reiniciar o Nó zera tudo.
- Sem ferramentas no agente do servidor por padrão (só conversa). Ferramentas exigem política de capacidades explícita.
- Atrás de proxy, o IP visto pelo servidor é o do proxy: o limite de tentativas falhas passa a ser compartilhado.
- Um pedido que estoura o tempo limite continua rodando no servidor até acabar (a vaga só é liberada ao fim).
- O app Android (`android/app/`) **compila** (o CI roda `:app:assembleDebug`), mas **nunca rodou em aparelho ou emulador** e não tem testes de interface; só o núcleo Kotlin tem testes.
