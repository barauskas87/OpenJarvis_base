"""Agendador de tarefas: cron/intervalo/uma vez, com polling em segundo plano.

Patch N10 (e N11 em ``tools.py``). Diferenças em relação ao upstream:

- cada tarefa vencida é REIVINDICADA antes de rodar (o próximo horário é
  gravado primeiro). Assim uma falha, um timeout ou um fuso inválido não faz a
  mesma tarefa rodar de novo a cada ciclo. A entrega passa a ser "no máximo
  uma vez" por disparo; se o processo cair no meio, aquele disparo se perde;
- a exceção de uma tarefa não aborta as demais do mesmo ciclo;
- cada tarefa tem timeout (``task_timeout``): o ``system.ask`` roda numa thread
  separada e, se estourar, o disparo é registrado como erro (a thread não pode
  ser morta; fica abandonada — por isso o limite é conservador);
- validação na criação: tipo, cron (``croniter``), ISO do "uma vez" (normalizado
  para UTC, para a comparação de texto do banco funcionar), intervalo mínimo,
  fuso (``zoneinfo``; no Windows exige o pacote ``tzdata``), tamanho do prompt
  e teto de tarefas ativas;
- resultado e erro vão para o log de execuções com segredos mascarados e
  truncados.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from openjarvis.scheduler.store import SchedulerStore
from openjarvis.security.scanner import SecretScanner

logger = logging.getLogger(__name__)

SCHEDULER_TASK_START = "scheduler_task_start"
SCHEDULER_TASK_END = "scheduler_task_end"

_TIPOS = ("cron", "interval", "once")
_MAX_PROMPT = 4000
_MAX_RESULTADO = 10_000


@dataclass(slots=True)
class ScheduledTask:
    """Uma tarefa agendada (única ou recorrente)."""

    id: str
    prompt: str
    schedule_type: str  # "cron" | "interval" | "once"
    schedule_value: str  # expressão cron, segundos ou data ISO
    context_mode: str = "isolated"
    status: str = "active"
    next_run: Optional[str] = None
    last_run: Optional[str] = None
    agent: str = "simple"
    tools: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "prompt": self.prompt,
            "schedule_type": self.schedule_type,
            "schedule_value": self.schedule_value,
            "context_mode": self.context_mode,
            "status": self.status,
            "next_run": self.next_run,
            "last_run": self.last_run,
            "agent": self.agent,
            "tools": self.tools,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ScheduledTask":
        return cls(
            id=d["id"],
            prompt=d["prompt"],
            schedule_type=d["schedule_type"],
            schedule_value=d["schedule_value"],
            context_mode=d.get("context_mode", "isolated"),
            status=d.get("status", "active"),
            next_run=d.get("next_run"),
            last_run=d.get("last_run"),
            agent=d.get("agent", "simple"),
            tools=d.get("tools", ""),
            metadata=d.get("metadata", {}),
        )


def _now_iso() -> str:
    """Agora em UTC, formato ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


def _para_utc_iso(valor: str) -> str:
    """Converte uma data ISO (com ou sem fuso; ``Z`` aceito) para UTC ISO.

    Sem fuso informado, assume UTC. Levanta ``ValueError`` se inválida.
    """
    texto = valor.strip()
    if texto.endswith(("Z", "z")):
        texto = texto[:-1] + "+00:00"
    momento = datetime.fromisoformat(texto)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc).isoformat()


def _normalizar_fuso(nome: str) -> ZoneInfo:
    try:
        return ZoneInfo(nome)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise ValueError(
            f"Fuso horário inválido ou indisponível: {nome!r}. "
            "No Windows instale o pacote 'tzdata'."
        ) from exc


class TaskScheduler:
    """Agendador que consulta tarefas vencidas e as executa."""

    def __init__(
        self,
        store: SchedulerStore,
        system: Any = None,
        *,
        poll_interval: int = 60,
        bus: Any = None,
        task_timeout: float = 600.0,
        min_interval_seconds: float = 60.0,
        max_active_tasks: int = 50,
    ) -> None:
        self._store = store
        self._system = system
        self._poll_interval = poll_interval
        self._bus = bus
        self._task_timeout = task_timeout
        self._min_interval = min_interval_seconds
        self._max_active = max_active_tasks
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._redator = SecretScanner()

    # -- API pública ----------------------------------------------------------

    def start(self) -> None:
        """Inicia a thread de polling (idempotente)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="jarvis-scheduler"
        )
        self._thread.start()
        logger.info("Scheduler started (poll_interval=%ds)", self._poll_interval)

    def stop(self) -> None:
        """Pede parada e espera a thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._poll_interval + 5)
            self._thread = None
        logger.info("Scheduler stopped")

    def _validar(
        self,
        prompt: str,
        schedule_type: str,
        schedule_value: str,
        metadata: Dict[str, Any],
    ) -> str:
        """Valida os dados e devolve o ``schedule_value`` normalizado."""
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt vazio")
        if len(prompt) > _MAX_PROMPT:
            raise ValueError(f"prompt maior que {_MAX_PROMPT} caracteres")
        if schedule_type not in _TIPOS:
            raise ValueError(f"schedule_type deve ser um de {_TIPOS}")
        valor = str(schedule_value).strip()
        fuso = (metadata or {}).get("timezone")
        if fuso:
            _normalizar_fuso(str(fuso))
        if schedule_type == "interval":
            try:
                segundos = float(valor)
            except ValueError as exc:
                raise ValueError("intervalo deve ser um número de segundos") from exc
            if segundos < self._min_interval:
                raise ValueError(f"intervalo mínimo é {self._min_interval:.0f}s")
            return str(segundos)
        if schedule_type == "cron":
            from croniter import croniter

            if not croniter.is_valid(valor):
                raise ValueError(f"expressão cron inválida: {valor!r}")
            return valor
        try:
            return _para_utc_iso(valor)
        except ValueError as exc:
            raise ValueError(f"data ISO inválida: {valor!r}") from exc

    def create_task(
        self,
        prompt: str,
        schedule_type: str,
        schedule_value: str,
        **kwargs: Any,
    ) -> ScheduledTask:
        """Valida, calcula o primeiro disparo e persiste a tarefa."""
        metadata = kwargs.get("metadata", {}) or {}
        valor = self._validar(prompt, schedule_type, schedule_value, metadata)
        with self._lock:
            ativas = len(self._store.list_tasks(status="active"))
            if ativas >= self._max_active:
                raise ValueError(f"limite de {self._max_active} tarefas ativas")
            tarefa = ScheduledTask(
                id=uuid.uuid4().hex[:16],
                prompt=prompt,
                schedule_type=schedule_type,
                schedule_value=valor,
                agent=kwargs.get("agent", "simple"),
                tools=kwargs.get("tools", ""),
                context_mode=kwargs.get("context_mode", "isolated"),
                metadata=metadata,
            )
            tarefa.next_run = self._compute_next_run(tarefa)
            self._store.save_task(tarefa.to_dict())
        return tarefa

    def list_tasks(self, *, status: Optional[str] = None) -> List[ScheduledTask]:
        with self._lock:
            linhas = self._store.list_tasks(status=status)
        return [ScheduledTask.from_dict(r) for r in linhas]

    def _alterar_status(self, task_id: str, status: str) -> None:
        with self._lock:
            d = self._store.get_task(task_id)
            if d is None:
                raise KeyError(f"Task not found: {task_id}")
            d["status"] = status
            if status == "active":
                d["next_run"] = self._compute_next_run(ScheduledTask.from_dict(d))
            elif status == "cancelled":
                d["next_run"] = None
            self._store.update_task(d)

    def pause_task(self, task_id: str) -> None:
        self._alterar_status(task_id, "paused")

    def resume_task(self, task_id: str) -> None:
        self._alterar_status(task_id, "active")

    def cancel_task(self, task_id: str) -> None:
        self._alterar_status(task_id, "cancelled")

    # -- laço de polling ---------------------------------------------------

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                with self._lock:
                    vencidas = self._store.get_due_tasks(_now_iso())
            except Exception:  # noqa: BLE001
                logger.exception("Scheduler poll error")
                vencidas = []
            for linha in vencidas:
                if self._stop_event.is_set():
                    break
                try:
                    self._execute_task(ScheduledTask.from_dict(linha))
                except Exception:  # noqa: BLE001 — uma tarefa ruim não aborta as outras
                    logger.exception("Falha ao executar tarefa %s", linha.get("id"))
            self._stop_event.wait(timeout=self._poll_interval)

    def _reivindicar(self, tarefa: ScheduledTask) -> bool:
        """Grava o próximo disparo ANTES de executar. False se já não vale."""
        with self._lock:
            d = self._store.get_task(tarefa.id)
            if d is None or d.get("status") != "active":
                return False
            agora = _now_iso()
            d["last_run"] = agora
            atual = ScheduledTask.from_dict(d)
            try:
                proximo = self._compute_next_run(atual)
            except Exception:  # noqa: BLE001 — fuso/cron corrompido
                logger.exception(
                    "Tarefa %s com agendamento inválido; pausada", tarefa.id
                )
                d["status"] = "paused"
                d["next_run"] = None
                self._store.update_task(d)
                return False
            d["next_run"] = proximo
            if proximo is None:
                d["status"] = "running"  # "uma vez": conclui depois da execução
            self._store.update_task(d)
        return True

    def _perguntar_com_timeout(self, prompt: str, kwargs: Dict[str, Any]) -> str:
        """Roda ``system.ask`` numa thread e desiste depois de ``task_timeout``."""
        caixa: Dict[str, Any] = {}

        def alvo() -> None:
            try:
                caixa["ok"] = self._system.ask(prompt, **kwargs)
            except BaseException as exc:  # noqa: BLE001
                caixa["erro"] = exc

        thread = threading.Thread(target=alvo, daemon=True, name="jarvis-task")
        thread.start()
        thread.join(self._task_timeout)
        if thread.is_alive():
            raise TimeoutError(f"tarefa excedeu {self._task_timeout:.0f}s")
        if "erro" in caixa:
            raise caixa["erro"]
        return str(caixa.get("ok", ""))

    def _limpar(self, texto: str) -> str:
        return self._redator.redact(texto)[:_MAX_RESULTADO]

    def _execute_task(self, tarefa: ScheduledTask) -> None:
        """Executa uma tarefa vencida e registra o resultado."""
        if not self._reivindicar(tarefa):
            return
        inicio = _now_iso()
        if self._bus is not None:
            self._bus.publish(
                SCHEDULER_TASK_START, {"task_id": tarefa.id, "prompt": tarefa.prompt}
            )

        sucesso, resultado, erro = False, "", ""
        try:
            if self._system is not None:
                bruto = (
                    tarefa.tools
                    if isinstance(tarefa.tools, list)
                    else str(tarefa.tools).split(",")
                )
                ferramentas = [t.strip() for t in bruto if t.strip()]
                kwargs: Dict[str, Any] = {
                    "agent": tarefa.agent,
                    "tools": ferramentas or None,
                }
                meta = tarefa.metadata or {}
                if meta.get("operator_id"):
                    kwargs["system_prompt"] = meta.get("system_prompt", "")
                    kwargs["operator_id"] = meta["operator_id"]
                resultado = self._perguntar_com_timeout(tarefa.prompt, kwargs)
            else:
                resultado = f"[dry-run] Would execute: {tarefa.prompt}"
            sucesso = True
        except Exception as exc:  # noqa: BLE001
            erro = f"{exc.__class__.__name__}: {exc}"
            logger.error("Task %s failed: %s", tarefa.id, erro)

        fim = _now_iso()
        with self._lock:
            self._store.log_run(
                task_id=tarefa.id,
                started_at=inicio,
                finished_at=fim,
                success=sucesso,
                result=self._limpar(resultado),
                error=self._limpar(erro),
            )
            d = self._store.get_task(tarefa.id)
            if d is not None and d.get("status") == "running":
                d["status"] = "completed"
                self._store.update_task(d)

        if self._bus is not None:
            self._bus.publish(
                SCHEDULER_TASK_END,
                {
                    "task_id": tarefa.id,
                    "success": sucesso,
                    "result": self._limpar(resultado),
                    "error": self._limpar(erro),
                },
            )

    # -- cálculo do próximo disparo -------------------------------------------

    def _compute_next_run(self, tarefa: ScheduledTask) -> Optional[str]:
        """Próximo disparo em UTC ISO, ou ``None`` se não deve rodar de novo."""
        agora = datetime.now(timezone.utc)

        if tarefa.schedule_type == "once":
            if tarefa.last_run is not None:
                return None
            return _para_utc_iso(tarefa.schedule_value)

        if tarefa.schedule_type == "interval":
            return (agora + timedelta(seconds=float(tarefa.schedule_value))).isoformat()

        if tarefa.schedule_type == "cron":
            fuso = str((tarefa.metadata or {}).get("timezone") or "") or None
            return self._compute_next_cron(tarefa.schedule_value, agora, fuso)

        return None

    @staticmethod
    def _compute_next_cron(
        cron_expr: str,
        now: datetime,
        timezone_name: str | None = None,
    ) -> Optional[str]:
        """Próximo disparo cron, avaliado no fuso informado e gravado em UTC."""
        from croniter import croniter

        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        local = (
            now.astimezone(_normalizar_fuso(timezone_name)) if timezone_name else now
        )
        proximo = croniter(cron_expr, local).get_next(datetime)
        if proximo.tzinfo is None:
            proximo = proximo.replace(tzinfo=local.tzinfo)
        return proximo.astimezone(timezone.utc).isoformat()


__all__ = [
    "SCHEDULER_TASK_END",
    "SCHEDULER_TASK_START",
    "ScheduledTask",
    "TaskScheduler",
]
