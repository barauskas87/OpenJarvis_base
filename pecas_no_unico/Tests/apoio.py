"""Dublês de teste compartilhados (sem rede, sem modelo real)."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from openjarvis.core.types import ToolResult
from openjarvis.engine._stubs import InferenceEngine, StreamChunk
from openjarvis.tools._stubs import BaseTool, ToolSpec


class MotorRoteirizado(InferenceEngine):
    """Motor que devolve respostas prontas, em ordem, e guarda as chamadas."""

    engine_id = "roteirizado"

    def __init__(self, respostas: List[str]) -> None:
        self._respostas = list(respostas)
        self.chamadas: List[List[Any]] = []

    def generate(
        self,
        messages: Sequence[Any],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        self.chamadas.append(list(messages))
        texto = self._respostas.pop(0) if self._respostas else "Final Answer: fim"
        return {
            "content": texto,
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "model": model,
            "finish_reason": "stop",
        }

    async def stream(self, messages, *, model, **kwargs):  # pragma: no cover
        yield ""

    def list_models(self) -> List[str]:
        return ["fake"]

    def health(self) -> bool:
        return True


class MotorDeStream(InferenceEngine):
    """Motor de streaming com pedaços definidos pelo teste."""

    engine_id = "stream"

    def __init__(self, pedacos: List[str], extras: List[StreamChunk] | None = None):
        self._pedacos = pedacos
        self._extras = extras or []

    def generate(self, messages, *, model, **kwargs):  # pragma: no cover
        return {"content": "".join(self._pedacos)}

    async def stream(self, messages, *, model, **kwargs):
        for p in self._pedacos:
            yield p

    async def stream_full(self, messages, *, model, **kwargs):
        for p in self._pedacos:
            yield StreamChunk(content=p)
        for extra in self._extras:
            yield extra

    def list_models(self) -> List[str]:
        return []

    def health(self) -> bool:
        return True


class FerramentaEco(BaseTool):
    """Ferramenta local de teste: devolve o texto recebido."""

    tool_id = "eco"
    is_local = True

    def __init__(self, nome: str = "eco", retorno: str | None = None, **spec_kw):
        self._nome = nome
        self._retorno = retorno
        self._spec_kw = spec_kw
        self.chamadas: List[Dict[str, Any]] = []

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self._nome,
            description="Devolve o texto.",
            parameters={
                "type": "object",
                "properties": {"texto": {"type": "string"}},
            },
            **self._spec_kw,
        )

    def execute(self, **params: Any) -> ToolResult:
        self.chamadas.append(params)
        conteudo = (
            self._retorno if self._retorno is not None else str(params.get("texto", ""))
        )
        return ToolResult(tool_name=self._nome, content=conteudo, success=True)


class FerramentaExterna(FerramentaEco):
    """Ferramenta NÃO local (is_local=False), como web/MCP."""

    is_local = False
