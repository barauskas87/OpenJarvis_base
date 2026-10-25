"""Persistent memory service: async fact extraction integrated into core.

``MemoryService`` runs fact extraction on a dedicated background thread so it
never blocks ``jarvis serve`` request handling or the ``jarvis chat`` REPL.
Callers hand off an exchange via :meth:`submit`, which enqueues the work and
returns immediately — the slow model call and disk write happen out of band.
The worker swallows every per-job error (including ``BrokenPipeError`` when a
client disconnects mid-extraction), so a flaky extraction model can never take
down the host process.

The service is started and stopped as part of the OpenJarvis lifecycle (see
``cli/serve.py`` and ``cli/chat_cmd.py``) and is configured through the
``[memory]`` section of ``config.toml``.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Any, List, Optional

from openjarvis.core.events import Event, EventBus, EventType
from openjarvis.memory.extractor import FactExtractor
from openjarvis.memory.store import (
    TRUST_AUTO,
    TRUST_UNTRUSTED,
    Fact,
    FactStore,
    create_fact_store,
)

logger = logging.getLogger(__name__)

# Only these severities suppress a whole exchange; see _blocks_exchange().
_BLOCKING_THREAT_LEVELS = frozenset({"high", "critical"})

# Sentinel pushed onto the queue to wake the worker for shutdown.
_STOP = object()


class _ResultadoSuspeito:
    """Resultado usado quando não foi possível varrer o texto."""

    is_clean = False
    threat_level = "high"


_RESULTADO_SUSPEITO = _ResultadoSuspeito()


class MemoryService:
    """Background long-term-memory extraction and persistence service."""

    def __init__(
        self,
        store: FactStore,
        extractor: FactExtractor,
        *,
        event_bus: EventBus | None = None,
        scanner: Any = None,
        max_queue: int = 256,
        incluir_resposta: bool = False,
        exigir_revisao: bool = True,
    ) -> None:
        self._store = store
        self._extractor = extractor
        self._event_bus = event_bus
        self._scanner = scanner
        self._subscribed = False
        # Patch N21: por padrão só o texto do USUÁRIO é analisado (a resposta
        # do assistente pode refletir conteúdo web) e todo fato novo fica em
        # quarentena até alguém promovê-lo (``promote_reviewed``).
        self._incluir_resposta = incluir_resposta
        self._exigir_revisao = exigir_revisao
        self._queue: "queue.Queue[Any]" = queue.Queue(maxsize=max(1, max_queue))
        self._thread: Optional[threading.Thread] = None
        self._running = threading.Event()

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        """Start the background worker thread (idempotent)."""
        if self._running.is_set():
            return
        self._running.set()
        self._subscribe_events()
        self._thread = threading.Thread(
            target=self._loop,
            name="memory-service",
            daemon=True,
        )
        self._thread.start()
        logger.debug("Memory service started")

    def stop(self, timeout: float = 2.0) -> None:
        """Signal the worker to drain and stop, then join it (idempotent)."""
        if not self._running.is_set():
            return
        self._running.clear()
        try:
            self._queue.put_nowait(_STOP)
        except queue.Full:
            pass  # worker will notice the cleared flag on its next loop
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._thread = None
        self._unsubscribe_events()
        logger.debug("Memory service stopped")

    @property
    def is_running(self) -> bool:
        return self._running.is_set()

    # -- submission ---------------------------------------------------------

    def submit(self, user_text: str, assistant_text: str = "") -> bool:
        """Queue an exchange for extraction. Non-blocking; never raises.

        Returns True if the job was enqueued, False if the service is not
        running or the queue is full (in which case the exchange is dropped
        rather than blocking the caller — extraction is best-effort).
        """
        if not self._running.is_set():
            return False
        if not user_text or not user_text.strip():
            return False
        try:
            self._queue.put_nowait((user_text, assistant_text))
            return True
        except queue.Full:
            logger.debug("Memory service queue full; dropping exchange")
            return False

    def _subscribe_events(self) -> None:
        """Subscribe to lifecycle events that feed automatic memory."""
        if self._event_bus is None or self._subscribed:
            return
        self._event_bus.subscribe(
            EventType.CHAT_EXCHANGE_COMPLETED,
            self._on_completed_exchange,
        )
        self._subscribed = True

    def _unsubscribe_events(self) -> None:
        """Unsubscribe from lifecycle events (idempotent)."""
        if self._event_bus is None or not self._subscribed:
            return
        self._event_bus.unsubscribe(
            EventType.CHAT_EXCHANGE_COMPLETED,
            self._on_completed_exchange,
        )
        self._subscribed = False

    def _on_completed_exchange(self, event: Event) -> None:
        """Queue a completed chat exchange published on the event bus."""
        data = event.data or {}
        self.submit(
            str(data.get("user_text", "") or ""),
            str(data.get("assistant_text", "") or ""),
        )

    # -- worker -------------------------------------------------------------

    def _loop(self) -> None:
        while True:
            try:
                job = self._queue.get(timeout=0.5)
            except queue.Empty:
                if not self._running.is_set():
                    break
                continue
            if job is _STOP:
                self._queue.task_done()
                break
            try:
                self._process(job)
            except Exception:  # noqa: BLE001 — a bad job must not kill the worker
                logger.debug("Memory extraction job failed", exc_info=True)
            finally:
                self._queue.task_done()
            if not self._running.is_set() and self._queue.empty():
                break

    def _scan(self, text: str) -> Optional[Any]:
        """Roda o scanner de injeção. Falha FECHADA.

        Patch N21: o upstream seguia em frente quando o scanner falhava
        ("fail-open"). Agora, sem scanner ou com erro, devolve um resultado
        marcado como suspeito e o fato vai para a quarentena.
        """
        if self._scanner is None:
            return _RESULTADO_SUSPEITO
        try:
            return self._scanner.scan(text)
        except BaseException as exc:  # noqa: BLE001
            rust_panic = (
                exc.__class__.__module__ == "pyo3_runtime"
                and exc.__class__.__name__ == "PanicException"
            )
            if not isinstance(exc, Exception) and not rust_panic:
                raise
            logger.warning("Injection scan failed; quarantining (fail-closed)")
            return _RESULTADO_SUSPEITO

    @staticmethod
    def _flagged(result: Any) -> bool:
        """True if *result* carries any finding at all."""
        return result is not None and not getattr(result, "is_clean", True)

    @classmethod
    def _blocks_exchange(cls, result: Any) -> bool:
        """True only for a *severe* finding.

        Dropping an exchange is destructive and unrecoverable, so it is
        reserved for HIGH/CRITICAL hits. Lower-severity patterns (a pasted
        shell one-liner, a role-delimiter fence quoted in a code discussion)
        are ordinary developer traffic; those exchanges are still extracted,
        and anything suspicious is caught per-fact by the quarantine tier.
        """
        if not cls._flagged(result):
            return False
        level = getattr(result, "threat_level", "")
        name = str(getattr(level, "value", level) or "").strip().lower()
        return name in _BLOCKING_THREAT_LEVELS

    def _process(self, job: Any) -> None:
        user_text, assistant_text = job
        # Só o texto do usuário entra, salvo opção explícita.
        assistant_text = assistant_text if self._incluir_resposta else ""
        if self._blocks_exchange(self._scan(f"{user_text}\n{assistant_text}")):
            logger.info("Memory extraction skipped: injection detected in exchange")
            return
        facts = self._extractor.extract(user_text, assistant_text)
        if not facts:
            return
        limpos: List[str] = []
        quarentena: List[str] = []
        for fact in facts:
            suspeito = self._flagged(self._scan(fact))
            if suspeito or self._exigir_revisao:
                quarentena.append(fact)
            else:
                limpos.append(fact)
        stored = self._store.add_many_with_trust(
            limpos, source="auto", trust=TRUST_AUTO
        )
        if quarentena:
            stored += self._store.add_many_with_trust(
                quarentena, source="auto", trust=TRUST_UNTRUSTED
            )
            logger.info(
                "Memory: %d fato(s) em quarentena aguardando revisão", len(quarentena)
            )
        if stored:
            logger.debug("Memory service stored %d new fact(s)", stored)

    # -- store passthroughs -------------------------------------------------

    def list_facts(self) -> List[Fact]:
        return self._store.list()

    def clear_facts(self) -> int:
        return self._store.clear()

    def fact_count(self) -> int:
        return self._store.count()


def build_memory_service(
    config: Any,
    engine: Any,
    default_model: str = "",
    *,
    event_bus: EventBus | None = None,
) -> Optional[MemoryService]:
    """Build a :class:`MemoryService` from config, or ``None`` if disabled.

    Reads the ``[memory]`` section (``config.memory`` / ``config.tools.storage``)
    for ``enabled``, ``backend``, ``extraction_model``, ``max_facts`` and
    ``facts_path``.  Returns ``None`` when memory is disabled or no engine /
    extraction model is available, so callers can simply do::

        svc = build_memory_service(config, engine, model)
        if svc is not None:
            svc.start()
    """
    mem = getattr(config, "memory", None)
    if mem is None or not getattr(mem, "enabled", False):
        return None
    if engine is None:
        return None

    model = getattr(mem, "extraction_model", "") or default_model
    if not model:
        logger.debug("Memory service disabled: no extraction model available")
        return None

    store = create_fact_store(
        getattr(mem, "backend", "local"),
        path=getattr(mem, "facts_path", None),
        max_facts=getattr(mem, "max_facts", 1000),
    )
    extractor = FactExtractor(engine, model)
    return MemoryService(
        store, extractor, event_bus=event_bus, scanner=_build_scanner()
    )


def _build_scanner() -> Any:
    """Construct an injection scanner, or ``None`` if unavailable. Never raises —
    memory must work even if the security module can't load."""
    try:
        from openjarvis.security.injection_scanner import InjectionScanner

        return InjectionScanner()
    except Exception:  # noqa: BLE001 — scanner is an optional defence layer
        logger.debug(
            "Injection scanner unavailable; memory capture unguarded", exc_info=True
        )
        return None


def publish_completed_exchange(
    bus: EventBus | None,
    user_text: str,
    assistant_text: str = "",
    *,
    source: str = "",
) -> bool:
    """Publish a completed chat exchange for lifecycle subscribers."""
    if bus is None or not user_text or not user_text.strip():
        return False
    bus.publish(
        EventType.CHAT_EXCHANGE_COMPLETED,
        {
            "user_text": user_text,
            "assistant_text": assistant_text or "",
            "source": source,
        },
    )
    return True


__all__ = ["MemoryService", "build_memory_service", "publish_completed_exchange"]
