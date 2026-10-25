"""API HTTP do Nó (FastAPI) usada pelo app Android e por outros clientes.

Princípios:
- toda rota, exceto ``/v1/saude``, exige token de portador;
- o corpo é lido com teto de tamanho ANTES de ser interpretado;
- erros têm formato único e nunca repetem o que o cliente enviou;
- a resposta passa pelo removedor de segredos antes de sair;
- a concorrência é limitada (um pedido lento não derruba o Nó);
- o histórico de cada conversa pertence ao token que a iniciou.

TLS não é feito aqui: ver ``principal.py`` (certificado próprio ou proxy).
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
import uuid
from typing import Callable, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from openjarvis.security.rate_limiter import RateLimitConfig, RateLimiter
from openjarvis.security.scanner import SecretScanner
from openjarvis.servidor.autenticacao import AutenticadorToken
from openjarvis.servidor.conversador import Conversador
from openjarvis.servidor.historico import HistoricoDeConversas
from openjarvis.servidor.modelos import (
    PedidoConversa,
    RespostaConversa,
    RespostaErro,
    RespostaSaude,
)

logger = logging.getLogger(__name__)

VERSAO_API = "1"

_DESCRICAO_DOS_ERROS = {
    400: "JSON inválido",
    401: "Token ausente ou inválido",
    413: "Corpo maior que o limite",
    422: "Campos inválidos",
    429: "Limite de uso ou de tentativas",
    500: "Erro interno",
    503: "Nó ocupado",
    504: "Tempo esgotado",
}


def _erro(
    status: int,
    codigo: str,
    mensagem: str,
    cabecalhos: Optional[Dict[str, str]] = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"erro": codigo, "mensagem": mensagem},
        headers=cabecalhos,
    )


def _espera(segundos: float) -> Dict[str, str]:
    return {"Retry-After": str(max(1, math.ceil(segundos)))}


def _token_do_cabecalho(request: Request) -> Optional[str]:
    valor = request.headers.get("authorization", "")
    esquema, _, token = valor.partition(" ")
    if esquema.lower() != "bearer":
        return None
    return token.strip() or None


def criar_aplicacao(
    conversador: Conversador,
    autenticador: AutenticadorToken,
    *,
    historico: Optional[HistoricoDeConversas] = None,
    tamanho_max_corpo: int = 64 * 1024,
    requisicoes_por_minuto: int = 30,
    rajada: int = 10,
    falhas_por_minuto: int = 10,
    tempo_limite_s: float = 120.0,
    max_simultaneas: int = 4,
    relogio: Callable[[], float] = time.monotonic,
) -> FastAPI:
    """Monta a aplicação. Tudo que varia vem por parâmetro (testável sem rede)."""
    app = FastAPI(
        title="Nó Único",
        version=VERSAO_API,
        # Sem páginas de documentação públicas; o esquema sai por app.openapi().
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    memoria = historico if historico is not None else HistoricoDeConversas()
    limite_uso = RateLimiter(
        RateLimitConfig(requests_per_minute=requisicoes_por_minuto, burst_size=rajada),
        relogio,
    )
    limite_falhas = RateLimiter(
        RateLimitConfig(
            requests_per_minute=falhas_por_minuto, burst_size=falhas_por_minuto
        ),
        relogio,
    )
    removedor = SecretScanner()
    # Criado na primeira requisição, dentro do laço de eventos em uso.
    estado: Dict[str, asyncio.Semaphore] = {}

    def semaforo() -> asyncio.Semaphore:
        if "s" not in estado:
            estado["s"] = asyncio.Semaphore(max_simultaneas)
        return estado["s"]

    @app.middleware("http")
    async def cabecalhos_de_seguranca(request: Request, call_next):
        resposta = await call_next(request)
        resposta.headers["Cache-Control"] = "no-store"
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        return resposta

    @app.get("/v1/saude", response_model=RespostaSaude)
    async def saude() -> RespostaSaude:
        return RespostaSaude(status="ok", versao_api=VERSAO_API)

    @app.post(
        "/v1/conversar",
        response_model=RespostaConversa,
        # Descrições fixas: o texto padrão do FastAPI vem de ``http.HTTPStatus``
        # e muda entre versões do Python, o que mudaria o contrato sem querer.
        responses={
            codigo: {"model": RespostaErro, "description": descricao}
            for codigo, descricao in _DESCRICAO_DOS_ERROS.items()
        },
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"schema": PedidoConversa.model_json_schema()}
                },
            }
        },
    )
    async def conversar(request: Request):
        # 1) autenticação (antes de ler o corpo)
        dono = autenticador.identificar(_token_do_cabecalho(request))
        if dono is None:
            origem = request.client.host if request.client else "desconhecida"
            permitido, espera = limite_falhas.check(origem)
            if not permitido:
                return _erro(429, "muitas_tentativas", "Aguarde.", _espera(espera))
            return _erro(
                401,
                "nao_autorizado",
                "Token ausente ou inválido.",
                {"WWW-Authenticate": "Bearer"},
            )

        # 2) limite de uso por token
        permitido, espera = limite_uso.check(dono)
        if not permitido:
            return _erro(429, "limite_de_uso", "Muitos pedidos.", _espera(espera))

        # 3) corpo com teto (cabeçalho e leitura em pedaços)
        declarado = request.headers.get("content-length")
        if declarado is not None:
            try:
                if int(declarado) > tamanho_max_corpo:
                    return _erro(413, "corpo_grande", "Corpo grande demais.")
            except ValueError:
                return _erro(400, "requisicao_invalida", "Cabeçalho inválido.")
        bruto = bytearray()
        async for pedaco in request.stream():
            bruto.extend(pedaco)
            if len(bruto) > tamanho_max_corpo:
                return _erro(413, "corpo_grande", "Corpo grande demais.")

        # 4) interpretação e validação (sem ecoar o conteúdo recebido)
        try:
            dados = json.loads(bytes(bruto))
        except (ValueError, RecursionError):
            return _erro(400, "json_invalido", "O corpo não é um JSON válido.")
        try:
            pedido = PedidoConversa.model_validate(dados)
        except ValidationError as exc:
            campos = sorted({str(e["loc"][0]) for e in exc.errors() if e["loc"]})
            return _erro(
                422, "pedido_invalido", "Campos inválidos: " + ", ".join(campos) + "."
            )

        # 5) concorrência limitada
        sem = semaforo()
        if sem.locked():
            return _erro(503, "ocupado", "Nó ocupado. Tente de novo.", _espera(1))
        await sem.acquire()
        laco = asyncio.get_running_loop()

        conversa_id = pedido.conversa_id or uuid.uuid4().hex
        anteriores = memoria.obter(dono, conversa_id)

        def trabalho():
            try:
                return conversador.conversar(pedido.mensagem, anteriores)
            finally:
                # Libera a vaga só quando a thread termina de fato, mesmo que o
                # cliente já tenha recebido 504: o limite vale para o trabalho real.
                try:
                    laco.call_soon_threadsafe(sem.release)
                except RuntimeError:  # laço já encerrado (desligamento)
                    pass

        try:
            resultado = await asyncio.wait_for(
                run_in_threadpool(trabalho), tempo_limite_s
            )
        except asyncio.TimeoutError:
            return _erro(504, "tempo_esgotado", "A resposta demorou demais.")
        except Exception:  # noqa: BLE001 — nada de detalhe interno para o cliente
            logger.exception("Falha ao conversar")
            return _erro(500, "falha_interna", "Erro interno.")

        resposta = removedor.redact(resultado.resposta)
        memoria.registrar(dono, conversa_id, pedido.mensagem, resposta)
        return RespostaConversa(
            resposta=resposta, conversa_id=conversa_id, turnos=int(resultado.turnos)
        )

    return app


__all__ = ["VERSAO_API", "criar_aplicacao"]
