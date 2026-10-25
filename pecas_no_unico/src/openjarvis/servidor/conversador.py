"""Ponte entre a API e o agente.

``Conversador`` é a interface mínima que a API usa; assim a API é testada sem
modelo e o agente real entra só na montagem final.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Protocol, Tuple

from openjarvis.agents._stubs import AgentContext, BaseAgent
from openjarvis.core.types import Conversation, Message, Role


@dataclass(slots=True)
class ResultadoConversa:
    resposta: str
    turnos: int


class Conversador(Protocol):
    """O que a API precisa de quem responde."""

    def conversar(
        self, mensagem: str, historico: List[Tuple[str, str]]
    ) -> ResultadoConversa: ...


class ConversadorAgente:
    """Responde usando um agente novo por pedido (sem estado compartilhado)."""

    def __init__(self, fabrica_do_agente: Callable[[], BaseAgent]) -> None:
        self._fabrica = fabrica_do_agente

    def conversar(
        self, mensagem: str, historico: List[Tuple[str, str]]
    ) -> ResultadoConversa:
        conversa = Conversation()
        for usuario, assistente in historico:
            conversa.add(Message(role=Role.USER, content=usuario))
            conversa.add(Message(role=Role.ASSISTANT, content=assistente))
        agente = self._fabrica()
        resultado = agente.run(mensagem, context=AgentContext(conversation=conversa))
        return ResultadoConversa(resposta=resultado.content, turnos=resultado.turns)
