"""TraceCollector — grava o rastro de cada execução de um agente.

Patch N23. Diferenças em relação ao upstream:

- isolamento entre execuções simultâneas: o barramento de eventos é global e
  chama os assinantes NA thread de quem publica. O upstream guardava o estado
  em atributos da instância e aceitava eventos de qualquer thread, então duas
  execuções ao mesmo tempo (servidor, agendador, Telegram) misturavam passos.
  Agora cada ``run`` cria seu próprio estado e só aceita eventos publicados
  pela própria thread;
- segredos são mascarados (``SecretScanner.redact``) em consulta, resposta,
  mensagens e em todos os passos antes de gravar no SQLite;
- a gravação do trace nunca derruba a resposta ao usuário.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from openjarvis.agents._stubs import AgentContext, AgentResult, BaseAgent
from openjarvis.core.events import EventBus, EventType
from openjarvis.core.types import StepType, Trace, TraceStep
from openjarvis.security.scanner import SecretScanner
from openjarvis.traces.store import TraceStore

logger = logging.getLogger(__name__)


def _mascarar(valor: Any, scanner: SecretScanner) -> Any:
    """Mascara segredos em qualquer estrutura de dict/list/str."""
    if isinstance(valor, str):
        return scanner.redact(valor)
    if isinstance(valor, dict):
        return {k: _mascarar(v, scanner) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_mascarar(v, scanner) for v in valor]
    return valor


class _Execucao:
    """Estado de UMA execução (não compartilhado entre threads)."""

    def __init__(self, thread_id: int) -> None:
        self.thread_id = thread_id
        self.passos: List[TraceStep] = []
        self.modelo = ""
        self.engine = ""
        self.inicio_inferencia: Optional[float] = None
        self.inicio_ferramenta: Optional[float] = None
        self.dados_ferramenta: Dict[str, Any] = {}


class TraceCollector:
    """Envolve um ``BaseAgent`` e grava um ``Trace`` por ``run()``."""

    def __init__(
        self,
        agent: BaseAgent,
        *,
        store: Optional[TraceStore] = None,
        bus: Optional[EventBus] = None,
    ) -> None:
        self._agent = agent
        self._store = store
        self._bus = bus
        self._scanner = SecretScanner()
        self._ultimo: Optional[Trace] = None
        self._trava = threading.Lock()

    # -- execução ----------------------------------------------------------

    def run(
        self,
        input: str,
        context: Optional[AgentContext] = None,
        **kwargs: Any,
    ) -> AgentResult:
        """Executa o agente e grava o trace."""
        execucao = _Execucao(threading.get_ident())
        desinscrever = self._inscrever(execucao)

        inicio = time.time()
        try:
            resultado = self._agent.run(input, context=context, **kwargs)
        finally:
            desinscrever()
        fim = time.time()

        execucao.passos.append(
            TraceStep(
                step_type=StepType.RESPOND,
                timestamp=fim,
                duration_seconds=0.0,
                output={"content": resultado.content, "turns": resultado.turns},
            )
        )

        trace = Trace(
            query=input,
            agent=getattr(self._agent, "agent_id", "unknown"),
            model=execucao.modelo,
            engine=execucao.engine,
            steps=list(execucao.passos),
            result=resultado.content,
            messages=resultado.metadata.get("messages", []),
            started_at=inicio,
            ended_at=fim,
        )
        for passo in trace.steps:
            trace.total_latency_seconds += passo.duration_seconds
            trace.total_tokens += passo.output.get("tokens", 0)

        trace = self._mascarar_trace(trace)
        with self._trava:
            self._ultimo = trace

        if self._store is not None:
            try:
                self._store.save(trace)
            except Exception:  # noqa: BLE001 — falha de gravação não afeta a resposta
                logger.exception("Falha ao gravar o trace %s", trace.trace_id)

        if self._bus is not None:
            self._bus.publish(EventType.TRACE_COMPLETE, {"trace": trace})
        return resultado

    @property
    def last_trace(self) -> Optional[Trace]:
        with self._trava:
            return self._ultimo

    # -- mascaramento ------------------------------------------------------

    def _mascarar_trace(self, trace: Trace) -> Trace:
        trace.query = self._scanner.redact(trace.query)
        trace.result = self._scanner.redact(trace.result)
        trace.messages = _mascarar(trace.messages, self._scanner)
        trace.metadata = _mascarar(trace.metadata, self._scanner)
        for passo in trace.steps:
            passo.input = _mascarar(passo.input, self._scanner)
            passo.output = _mascarar(passo.output, self._scanner)
            passo.metadata = _mascarar(passo.metadata, self._scanner)
        return trace

    # -- assinantes --------------------------------------------------------

    def _inscrever(self, execucao: _Execucao):
        """Registra assinantes ligados a ESTA execução; devolve o cancelador."""
        if self._bus is None:
            return lambda: None

        def so_minha_thread(tratar):
            def envoltorio(evento: Any) -> None:
                if threading.get_ident() == execucao.thread_id:
                    tratar(execucao, evento)

            return envoltorio

        pares = [
            (EventType.INFERENCE_START, so_minha_thread(self._ao_iniciar_inferencia)),
            (EventType.INFERENCE_END, so_minha_thread(self._ao_fim_inferencia)),
            (EventType.TOOL_CALL_START, so_minha_thread(self._ao_iniciar_ferramenta)),
            (EventType.TOOL_CALL_END, so_minha_thread(self._ao_fim_ferramenta)),
            (EventType.MEMORY_RETRIEVE, so_minha_thread(self._ao_recuperar_memoria)),
        ]
        for tipo, tratador in pares:
            self._bus.subscribe(tipo, tratador)

        def cancelar() -> None:
            for tipo, tratador in pares:
                self._bus.unsubscribe(tipo, tratador)

        return cancelar

    @staticmethod
    def _ao_iniciar_inferencia(exe: _Execucao, evento: Any) -> None:
        exe.modelo = evento.data.get("model", exe.modelo)
        exe.engine = evento.data.get("engine", exe.engine)
        exe.inicio_inferencia = evento.timestamp

    @staticmethod
    def _ao_fim_inferencia(exe: _Execucao, evento: Any) -> None:
        inicio = exe.inicio_inferencia or evento.timestamp
        dados = evento.data
        uso = dados.get("usage", {})
        exe.passos.append(
            TraceStep(
                step_type=StepType.GENERATE,
                timestamp=inicio,
                duration_seconds=evento.timestamp - inicio,
                input={"model": exe.modelo},
                output={
                    "prompt_tokens": uso.get("prompt_tokens", 0),
                    "completion_tokens": uso.get("completion_tokens", 0),
                    "total_tokens": uso.get("total_tokens", 0),
                    "tokens": uso.get("total_tokens", dados.get("total_tokens", 0)),
                    "content": dados.get("content", ""),
                    "tool_calls": dados.get("tool_calls", []),
                    "tool_results": dados.get("tool_results", []),
                    "content_blocks": dados.get("content_blocks", []),
                    "finish_reason": dados.get("finish_reason", ""),
                },
                metadata={"engine": exe.engine},
            )
        )

    @staticmethod
    def _ao_iniciar_ferramenta(exe: _Execucao, evento: Any) -> None:
        exe.inicio_ferramenta = evento.timestamp
        exe.dados_ferramenta = evento.data

    @staticmethod
    def _ao_fim_ferramenta(exe: _Execucao, evento: Any) -> None:
        inicio = exe.inicio_ferramenta or evento.timestamp
        exe.passos.append(
            TraceStep(
                step_type=StepType.TOOL_CALL,
                timestamp=inicio,
                duration_seconds=evento.data.get("latency", evento.timestamp - inicio),
                input={
                    "tool": evento.data.get("tool", ""),
                    "arguments": exe.dados_ferramenta.get("arguments", {}),
                },
                output={
                    "success": evento.data.get("success", False),
                    "result": evento.data.get("result", ""),
                },
                metadata=dict(evento.data.get("metadata") or {}),
            )
        )

    @staticmethod
    def _ao_recuperar_memoria(exe: _Execucao, evento: Any) -> None:
        exe.passos.append(
            TraceStep(
                step_type=StepType.RETRIEVE,
                timestamp=evento.timestamp,
                duration_seconds=evento.data.get("latency", 0.0),
                input={"query": evento.data.get("query", "")},
                output={"num_results": evento.data.get("num_results", 0)},
            )
        )


def record_response_trace(
    store: Optional[TraceStore],
    *,
    query: str,
    result: str,
    model: str = "",
    engine: str = "",
    agent: str = "server",
    started_at: float,
    ended_at: float,
) -> Optional[Trace]:
    """Grava um trace mínimo (de uma etapa) para respostas fora de agente."""
    if store is None:
        return None
    try:
        scanner = SecretScanner()
        duracao = max(0.0, ended_at - started_at)
        resultado = scanner.redact(result)
        trace = Trace(
            query=scanner.redact(query),
            agent=agent,
            model=model,
            engine=engine,
            result=resultado,
            started_at=started_at,
            ended_at=ended_at,
            steps=[
                TraceStep(
                    step_type=StepType.RESPOND,
                    timestamp=ended_at,
                    duration_seconds=duracao,
                    output={"content": resultado},
                )
            ],
        )
        trace.total_latency_seconds = duracao
        store.save(trace)
        return trace
    except Exception:  # noqa: BLE001
        logger.debug("record_response_trace failed", exc_info=True)
        return None


__all__ = ["TraceCollector", "record_response_trace"]
