"""Adaptador de ferramentas MCP para ``BaseTool``.

Patch N20. Diferenças em relação ao upstream:

- o nome exposto ao agente é com prefixo do servidor (``mcp__<servidor>__<nome>``),
  então uma ferramenta remota chamada ``shell_exec`` não colide nem substitui a
  nativa; o nome REMOTO original é guardado só para a chamada;
- ``is_local = False`` (padrão do BaseTool): a saída passa pelo cerco de
  injeção e o guarda de fronteira vê os argumentos;
- exige confirmação por padrão (``requires_confirmation=True``), a menos que o
  servidor seja marcado como confiável na configuração;
- saída truncada em 100 mil caracteres.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any, Iterable, List, Optional

from openjarvis.core.types import ToolResult
from openjarvis.mcp.client import MCPClient
from openjarvis.tools._stubs import BaseTool, ToolSpec

_MAX_SAIDA = 100_000
_SEGURO = re.compile(r"[^A-Za-z0-9_-]")


def nome_local(servidor: str, nome_remoto: str) -> str:
    """Nome exposto ao agente: ``mcp__<servidor>__<ferramenta>`` saneado."""
    return f"mcp__{_SEGURO.sub('_', servidor)}__{_SEGURO.sub('_', nome_remoto)}"


class MCPToolAdapter(BaseTool):
    """Envolve uma ferramenta hospedada em um servidor MCP."""

    tool_id = "mcp_adapter"

    def __init__(
        self,
        client: MCPClient,
        tool_spec: ToolSpec,
        *,
        servidor: str = "",
        exigir_confirmacao: bool = True,
        timeout_segundos: float = 120.0,
    ) -> None:
        self._client = client
        self._nome_remoto = tool_spec.name
        nome_exposto = (
            nome_local(servidor, tool_spec.name) if servidor else tool_spec.name
        )
        self._spec = dataclasses.replace(
            tool_spec,
            name=nome_exposto,
            requires_confirmation=exigir_confirmacao,
            timeout_seconds=timeout_segundos,
        )

    @property
    def spec(self) -> ToolSpec:
        return self._spec

    def execute(self, **params: Any) -> ToolResult:
        """Chama a ferramenta remota (pelo nome REMOTO) e devolve o texto."""
        try:
            resultado = self._client.call_tool(self._nome_remoto, params)
            partes = resultado.get("content", [])
            texto = "\n".join(
                str(p.get("text", "")) for p in partes if isinstance(p, dict)
            )
            if len(texto) > _MAX_SAIDA:
                texto = texto[:_MAX_SAIDA] + "\n[... truncado ...]"
            return ToolResult(
                tool_name=self._spec.name,
                content=texto,
                success=not resultado.get("isError", False),
            )
        except Exception as exc:  # noqa: BLE001 — erro remoto vira resultado
            return ToolResult(
                tool_name=self._spec.name,
                content=f"MCP tool error: {exc.__class__.__name__}: {exc}",
                success=False,
            )


class MCPToolProvider:
    """Descobre as ferramentas de um servidor MCP e devolve adaptadores."""

    def __init__(
        self,
        client: MCPClient,
        *,
        servidor: str = "",
        exigir_confirmacao: bool = True,
        timeout_segundos: float = 120.0,
    ) -> None:
        self._client = client
        self._servidor = servidor
        self._exigir_confirmacao = exigir_confirmacao
        self._timeout = timeout_segundos

    def discover(self, *, confiaveis: Optional[Iterable[str]] = None) -> List[BaseTool]:
        """Descobre ferramentas. ``confiaveis`` = nomes remotos sem confirmação."""
        liberadas = set(confiaveis or ())
        return [
            MCPToolAdapter(
                self._client,
                spec,
                servidor=self._servidor,
                exigir_confirmacao=(
                    self._exigir_confirmacao and spec.name not in liberadas
                ),
                timeout_segundos=self._timeout,
            )
            for spec in self._client.list_tools()
        ]


__all__ = ["MCPToolAdapter", "MCPToolProvider", "nome_local"]
