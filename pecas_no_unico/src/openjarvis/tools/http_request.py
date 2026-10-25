"""Ferramenta de requisição HTTP com proteção SSRF a cada salto.

Patches C1 e C2 (e demais). Diferenças em relação ao upstream:

- C1: sem ``os.path.expandvars`` nos cabeçalhos. O upstream expandia ``$VAR``
  nos cabeçalhos escolhidos pelo modelo, permitindo mandar
  ``Authorization: Bearer $OPENAI_API_KEY`` a um host qualquer;
- C2: sem o atalho Rust (que seguia redirecionamentos sem revalidar SSRF);
  todo salto de redirecionamento passa por ``check_ssrf``;
- a resposta é lida em fluxo com teto de 1 MB (o upstream baixava tudo para
  memória e só depois cortava);
- só ``http``/``https``; cabeçalhos de controle de conexão são recusados;
- o cliente HTTP é injetável (``transporte``) para testes sem rede.
"""

from __future__ import annotations

import logging
import time
import urllib.parse
from typing import Any, Optional

import httpx

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.security.ssrf import check_ssrf
from openjarvis.tools._stubs import BaseTool, ToolSpec

logger = logging.getLogger(__name__)

_MAX_RESPONSE_BYTES = 1_048_576  # 1 MB
_ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"})
_MAX_REDIRECTS = 5
_MAX_TIMEOUT = 120

# Cabeçalhos que o modelo não pode definir (controle de conexão/roteamento).
_CABECALHOS_PROIBIDOS = frozenset(
    {"host", "connection", "content-length", "transfer-encoding", "upgrade", "te"}
)


class _SSRFRedirectError(Exception):
    """O destino de um redirecionamento falhou na checagem SSRF."""


@ToolRegistry.register("http_request")
class HttpRequestTool(BaseTool):
    """Faz requisições HTTP a APIs externas com proteção SSRF."""

    tool_id = "http_request"
    is_local = False

    def __init__(self, *, transporte: Optional[httpx.BaseTransport] = None) -> None:
        # ``transporte`` existe para testes (httpx.MockTransport).
        self._transporte = transporte

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="http_request",
            description=(
                "Make an HTTP request to a URL. Supports GET, POST, PUT, DELETE,"
                " PATCH and HEAD. Includes SSRF protection against private IPs"
                " and cloud metadata."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to send the request to.",
                    },
                    "method": {
                        "type": "string",
                        "description": "HTTP method. Defaults to GET.",
                    },
                    "headers": {
                        "type": "object",
                        "description": "Optional HTTP headers as key-value pairs.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Optional request body (for POST, PUT, PATCH).",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Request timeout in seconds. Defaults to 30.",
                    },
                },
                "required": ["url"],
            },
            category="network",
            required_capabilities=["network:fetch"],
        )

    @staticmethod
    def _falha(mensagem: str) -> ToolResult:
        return ToolResult(tool_name="http_request", content=mensagem, success=False)

    def execute(self, **params: Any) -> ToolResult:
        url = params.get("url", "")
        if not url or not isinstance(url, str):
            return self._falha("No URL provided.")

        metodo = str(params.get("method") or "GET").upper()
        if metodo not in _ALLOWED_METHODS:
            return self._falha(
                f"Unsupported HTTP method: {metodo}."
                f" Allowed: {', '.join(sorted(_ALLOWED_METHODS))}."
            )

        erro_ssrf = check_ssrf(url)
        if erro_ssrf:
            return self._falha(f"SSRF protection blocked request: {erro_ssrf}")

        cabecalhos_in = params.get("headers") or {}
        if not isinstance(cabecalhos_in, dict):
            return self._falha("headers must be an object.")
        cabecalhos: dict[str, str] = {}
        for chave, valor in cabecalhos_in.items():
            nome = str(chave).strip()
            if nome.lower() in _CABECALHOS_PROIBIDOS:
                return self._falha(f"Header not allowed: {nome}")
            if any(c in nome for c in "\r\n:") or any(c in str(valor) for c in "\r\n"):
                return self._falha("Invalid header.")
            # Valor LITERAL: sem expansão de variáveis de ambiente (patch C1).
            cabecalhos[nome] = str(valor)

        corpo = params.get("body")
        try:
            tempo = float(params.get("timeout", 30))
        except (TypeError, ValueError):
            tempo = 30.0
        tempo = max(1.0, min(tempo, float(_MAX_TIMEOUT)))

        t0 = time.time()
        try:
            resposta, bruto, truncado = self._requisitar_com_redirects(
                metodo, url, cabecalhos=cabecalhos, corpo=corpo, tempo=tempo
            )
        except httpx.TimeoutException as exc:
            return self._falha(f"Request timed out after {tempo:.0f}s: {exc}")
        except _SSRFRedirectError as exc:
            return self._falha(f"SSRF protection blocked redirect: {exc}")
        except httpx.RequestError as exc:
            return self._falha(f"Request error: {exc.__class__.__name__}")
        except Exception as exc:  # noqa: BLE001 — a ferramenta nunca propaga
            return self._falha(f"Unexpected error: {exc.__class__.__name__}")
        decorrido_ms = (time.time() - t0) * 1000

        texto = bruto.decode(resposta.encoding or "utf-8", errors="replace")
        if truncado:
            texto += "\n\n[Response truncated at 1 MB]"
        return ToolResult(
            tool_name="http_request",
            content=texto,
            success=True,
            metadata={
                "status_code": resposta.status_code,
                "headers": dict(resposta.headers),
                "content_type": resposta.headers.get("content-type", ""),
                "elapsed_ms": round(decorrido_ms, 2),
                "truncated": truncado,
            },
        )

    def _requisitar_com_redirects(
        self,
        metodo: str,
        url: str,
        *,
        cabecalhos: dict[str, str],
        corpo: Any,
        tempo: float,
    ) -> tuple[httpx.Response, bytes, bool]:
        """Segue redirecionamentos à mão, revalidando SSRF em cada salto."""
        url_atual = url
        metodo_atual = metodo
        corpo_atual = corpo
        with httpx.Client(
            timeout=tempo, follow_redirects=False, transport=self._transporte
        ) as cliente:
            for _ in range(_MAX_REDIRECTS + 1):
                with cliente.stream(
                    metodo_atual,
                    url_atual,
                    headers=cabecalhos,
                    content=corpo_atual,
                ) as resposta:
                    if resposta.status_code in (301, 302, 303, 307, 308):
                        destino = resposta.headers.get("location", "")
                        if destino:
                            url_atual = urllib.parse.urljoin(str(resposta.url), destino)
                            erro = check_ssrf(url_atual)
                            if erro:
                                raise _SSRFRedirectError(erro)
                            # Ao mudar de host, nunca leva credenciais junto.
                            if urllib.parse.urlparse(url_atual).netloc != (
                                urllib.parse.urlparse(str(resposta.url)).netloc
                            ):
                                cabecalhos = {
                                    k: v
                                    for k, v in cabecalhos.items()
                                    if k.lower()
                                    not in (
                                        "authorization",
                                        "cookie",
                                        "proxy-authorization",
                                    )
                                }
                            if resposta.status_code in (301, 302, 303) and (
                                metodo_atual != "HEAD"
                            ):
                                metodo_atual = "GET"
                                corpo_atual = None
                            continue
                    pedacos: list[bytes] = []
                    total = 0
                    truncado = False
                    for pedaco in resposta.iter_bytes():
                        restante = _MAX_RESPONSE_BYTES - total
                        if len(pedaco) > restante:
                            pedacos.append(pedaco[:restante])
                            truncado = True
                            break
                        pedacos.append(pedaco)
                        total += len(pedaco)
                    return resposta, b"".join(pedacos), truncado
        raise _SSRFRedirectError(f"Exceeded maximum of {_MAX_REDIRECTS} redirects.")


__all__ = ["HttpRequestTool"]
