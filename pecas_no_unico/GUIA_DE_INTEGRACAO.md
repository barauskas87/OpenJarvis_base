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

## Servidor para o app Android
```bash
# 1) gerar um token (aparece uma vez) e o hash (vai para o servidor)
python -m openjarvis.servidor gerar-token

# 2) certificado autoassinado do Nó (ajuste nome e IP)
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 365 \
  -keyout chave.pem -out certificado.pem -subj "/CN=meu-no.local" \
  -addext "subjectAltName=DNS:meu-no.local,IP:192.168.0.10"

# 3) subir (o modelo vem de um servidor compatível com a API da OpenAI, ex. vLLM/llama.cpp)
export NO_UNICO_TOKEN_HASHES=<hash do passo 1>
python -m openjarvis.servidor servir --host 0.0.0.0 --porta 8443 \
  --certificado certificado.pem --chave chave.pem \
  --motor-host http://127.0.0.1:8000 --modelo NOME_DO_MODELO
```
No app: Configuração → endereço `https://192.168.0.10:8443`, token do passo 1 e o conteúdo de `certificado.pem`.

Atrás de um proxy com TLS (nginx/Caddy/Tailscale): use `--atras-de-proxy-tls --host 127.0.0.1` e deixe o app no
modo "autoridades do sistema". Teste local sem modelo: `python ferramentas/servidor_de_teste.py` (eco, TLS próprio).

## Cliente Kotlin
```bash
cd android
gradle :nucleo:test                                  # testes do cliente
NO_PYTHON=$(which python) gradle :nucleo:test        # inclui ponta a ponta com o servidor Python real
```
O módulo `:app` só entra no build quando há Android SDK (`ANDROID_HOME`); abra `android/` no Android Studio.
