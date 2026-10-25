# CONTRATO DA API — Nó Linux ⇄ app Android

Versão da API: **1**. Fonte da verdade: `contrato/openapi.json` (gerado do código) e os exemplos
em `contrato/*.json`. Os testes do servidor (Python) e os do cliente (Kotlin) leem os **mesmos** arquivos;
se um lado mudar sem o outro, um teste quebra.

## Segurança
- Só HTTPS. O servidor se recusa a escutar fora de `127.0.0.1` sem TLS (ou sem `--atras-de-proxy-tls`).
- Autenticação: `Authorization: Bearer <token>`. O servidor guarda só o hash SHA-256 do token.
- O app só aceita `https://` (exceção: `http://localhost` com a chave de desenvolvimento ligada).
- O app confia em (a) um certificado fixo (PEM) — recomendado para Nó em casa — ou (b) autoridades do
  sistema, com *pins* opcionais da chave pública.
- O app não segue redirecionamentos e não repete `POST` sozinho.

## Rotas
### `GET /v1/saude` (sem token)
`200 {"status":"ok","versao_api":"1"}`

### `POST /v1/conversar`
Pedido: `{"mensagem": "texto (1–8000 caracteres)", "conversa_id": "opcional, [A-Za-z0-9_-]{1,64}"}`
Resposta `200`: `{"resposta":"…","conversa_id":"…","turnos":1}`
- Sem `conversa_id` o servidor cria um e devolve; usar o mesmo nos pedidos seguintes continua a conversa.
- O histórico pertence ao token: outro token com o mesmo `conversa_id` não vê nada.
- A resposta passa por mascaramento de segredos (chaves de API, etc.).

## Erros (formato único `{"erro": "...", "mensagem": "..."}`)
| HTTP | `erro` | Significado | O app faz |
|---|---|---|---|
| 400 | `json_invalido` | corpo não é JSON | mostra erro |
| 401 | `nao_autorizado` | token ausente/inválido | pede novo token |
| 413 | `corpo_grande` | corpo > 64 KiB | mostra erro |
| 422 | `pedido_invalido` | campos inválidos (sem eco do conteúdo) | mostra erro |
| 429 | `limite_de_uso` / `muitas_tentativas` | `Retry-After` em segundos | espera |
| 500 | `falha_interna` | erro no Nó (sem detalhes) | mostra erro |
| 503 | `ocupado` | Nó no limite de pedidos simultâneos; `Retry-After` | espera |
| 504 | `tempo_esgotado` | modelo demorou mais que o limite | mostra erro |

## Como mudar o contrato
1. Altere `servidor/modelos.py` ou as rotas.
2. Regenere `contrato/openapi.json` (o teste `test_esquema_nao_mudou_sem_avisar` mostra a diferença).
3. Atualize as classes do cliente em `android/nucleo/` e os exemplos em `contrato/`.
4. Mudança que quebra clientes antigos = nova versão (`/v2/…`); acrescentar campo opcional na resposta não quebra
   (o cliente ignora campos desconhecidos).
