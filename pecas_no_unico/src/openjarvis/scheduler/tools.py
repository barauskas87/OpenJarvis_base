"""MCP tools for scheduler operations — schedule, list, pause, resume, cancel."""

from __future__ import annotations

import json
from typing import Any, Iterable, Optional

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.security.injection_scanner import InjectionScanner
from openjarvis.security.scanner import SecretScanner
from openjarvis.security.types import ThreatLevel
from openjarvis.tools._stubs import BaseTool, ToolSpec


@ToolRegistry.register("schedule_task")
class ScheduleTaskTool(BaseTool):
    """Agenda uma tarefa futura ou recorrente.

    Patch N11: no upstream o modelo podia agendar sem confirmação, escolhendo
    ``prompt``, ``agent`` e ``tools``; uma injeção de prompt virava execução
    recorrente persistente. Aqui:

    - exige confirmação humana e a capacidade ``schedule:create``;
    - ``agent`` e ``tools`` só podem ser os liberados no construtor (padrão:
      agente ``simple`` e nenhuma ferramenta);
    - o prompt é recusado se tiver segredo ou injeção grave.
    """

    tool_id = "schedule_task"
    _scheduler: Optional[Any] = None

    def __init__(
        self,
        scheduler: Optional[Any] = None,
        *,
        agentes_permitidos: Iterable[str] = ("simple",),
        ferramentas_permitidas: Iterable[str] = (),
    ) -> None:
        self._scheduler = scheduler
        self._agentes_permitidos = frozenset(agentes_permitidos)
        self._ferramentas_permitidas = frozenset(ferramentas_permitidas)
        self._injecao = InjectionScanner()
        self._segredos = SecretScanner()

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="schedule_task",
            description=(
                "Schedule a task for future or recurring execution. "
                "Supports cron expressions, interval (seconds), or "
                "one-time ISO datetime scheduling. Requires user confirmation."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The prompt/query to execute on schedule.",
                    },
                    "schedule_type": {
                        "type": "string",
                        "description": "Schedule type: 'cron', 'interval', or 'once'.",
                        "enum": ["cron", "interval", "once"],
                    },
                    "schedule_value": {
                        "type": "string",
                        "description": (
                            "Schedule value: cron expression, seconds for "
                            "interval, or ISO datetime for once."
                        ),
                    },
                    "agent": {
                        "type": "string",
                        "description": "Agent to use for execution (default: simple).",
                    },
                    "tools": {
                        "type": "string",
                        "description": "Comma-separated tool names for the agent.",
                    },
                },
                "required": ["prompt", "schedule_type", "schedule_value"],
            },
            category="scheduler",
            requires_confirmation=True,
            required_capabilities=["schedule:create"],
        )

    @staticmethod
    def _falha(mensagem: str) -> ToolResult:
        return ToolResult(tool_name="schedule_task", content=mensagem, success=False)

    def execute(self, **params: Any) -> ToolResult:
        if self._scheduler is None:
            return self._falha("Scheduler not available. Cannot schedule tasks.")
        prompt = params.get("prompt", "")
        schedule_type = params.get("schedule_type", "")
        schedule_value = params.get("schedule_value", "")
        if not prompt or not schedule_type or not schedule_value:
            return self._falha(
                "Missing required parameters: prompt, schedule_type, schedule_value."
            )

        agente = str(params.get("agent") or "simple")
        if agente not in self._agentes_permitidos:
            return self._falha(f"Agent not allowed for scheduled tasks: {agente}")

        bruto = params.get("tools") or ""
        pedidas = (
            [str(t).strip() for t in bruto if str(t).strip()]
            if isinstance(bruto, list)
            else [t.strip() for t in str(bruto).split(",") if t.strip()]
        )
        negadas = [t for t in pedidas if t not in self._ferramentas_permitidas]
        if negadas:
            return self._falha(f"Tools not allowed for scheduled tasks: {negadas}")

        if self._segredos.scan(str(prompt)).findings:
            return self._falha("Prompt contains secrets or credentials; refused.")
        analise = self._injecao.scan(str(prompt))
        if not analise.is_clean and analise.threat_level in (
            ThreatLevel.HIGH,
            ThreatLevel.CRITICAL,
        ):
            return self._falha("Prompt looks like a prompt injection; refused.")

        try:
            tarefa = self._scheduler.create_task(
                prompt=prompt,
                schedule_type=schedule_type,
                schedule_value=schedule_value,
                agent=agente,
                tools=",".join(pedidas),
            )
        except Exception as exc:  # noqa: BLE001 — erro de validação vira resultado
            return self._falha(f"Failed to schedule task: {exc}")
        return ToolResult(
            tool_name="schedule_task",
            content=json.dumps(
                {
                    "task_id": tarefa.id,
                    "next_run": tarefa.next_run,
                    "status": tarefa.status,
                }
            ),
            success=True,
        )


@ToolRegistry.register("list_scheduled_tasks")
class ListScheduledTasksTool(BaseTool):
    """List all scheduled tasks."""

    tool_id = "list_scheduled_tasks"
    _scheduler: Optional[Any] = None

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="list_scheduled_tasks",
            description="List all scheduled tasks, optionally filtered by status.",
            parameters={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": (
                            "Filter by status: 'active', 'paused', "
                            "'completed', 'cancelled'."
                        ),
                    },
                },
            },
            category="scheduler",
        )

    def execute(self, **params: Any) -> ToolResult:
        if self._scheduler is None:
            return ToolResult(
                tool_name="list_scheduled_tasks",
                content="Scheduler not available.",
                success=False,
            )
        try:
            status = params.get("status")
            tasks = self._scheduler.list_tasks(status=status)
            items = [t.to_dict() for t in tasks]
            return ToolResult(
                tool_name="list_scheduled_tasks",
                content=json.dumps(items, default=str),
                success=True,
            )
        except Exception as exc:
            return ToolResult(
                tool_name="list_scheduled_tasks",
                content=f"Failed to list tasks: {exc}",
                success=False,
            )


@ToolRegistry.register("pause_scheduled_task")
class PauseScheduledTaskTool(BaseTool):
    """Pause a scheduled task."""

    tool_id = "pause_scheduled_task"
    _scheduler: Optional[Any] = None

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="pause_scheduled_task",
            description="Pause an active scheduled task.",
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "ID of the task to pause.",
                    },
                },
                "required": ["task_id"],
            },
            category="scheduler",
        )

    def execute(self, **params: Any) -> ToolResult:
        if self._scheduler is None:
            return ToolResult(
                tool_name="pause_scheduled_task",
                content="Scheduler not available.",
                success=False,
            )
        task_id = params.get("task_id", "")
        if not task_id:
            return ToolResult(
                tool_name="pause_scheduled_task",
                content="Missing required parameter: task_id.",
                success=False,
            )
        try:
            self._scheduler.pause_task(task_id)
            return ToolResult(
                tool_name="pause_scheduled_task",
                content=f"Task {task_id} paused.",
                success=True,
            )
        except KeyError:
            return ToolResult(
                tool_name="pause_scheduled_task",
                content=f"Task not found: {task_id}",
                success=False,
            )
        except Exception as exc:
            return ToolResult(
                tool_name="pause_scheduled_task",
                content=f"Failed to pause task: {exc}",
                success=False,
            )


@ToolRegistry.register("resume_scheduled_task")
class ResumeScheduledTaskTool(BaseTool):
    """Resume a paused scheduled task."""

    tool_id = "resume_scheduled_task"
    _scheduler: Optional[Any] = None

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="resume_scheduled_task",
            description="Resume a paused scheduled task.",
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "ID of the task to resume.",
                    },
                },
                "required": ["task_id"],
            },
            category="scheduler",
        )

    def execute(self, **params: Any) -> ToolResult:
        if self._scheduler is None:
            return ToolResult(
                tool_name="resume_scheduled_task",
                content="Scheduler not available.",
                success=False,
            )
        task_id = params.get("task_id", "")
        if not task_id:
            return ToolResult(
                tool_name="resume_scheduled_task",
                content="Missing required parameter: task_id.",
                success=False,
            )
        try:
            self._scheduler.resume_task(task_id)
            return ToolResult(
                tool_name="resume_scheduled_task",
                content=f"Task {task_id} resumed.",
                success=True,
            )
        except KeyError:
            return ToolResult(
                tool_name="resume_scheduled_task",
                content=f"Task not found: {task_id}",
                success=False,
            )
        except Exception as exc:
            return ToolResult(
                tool_name="resume_scheduled_task",
                content=f"Failed to resume task: {exc}",
                success=False,
            )


@ToolRegistry.register("cancel_scheduled_task")
class CancelScheduledTaskTool(BaseTool):
    """Cancel a scheduled task."""

    tool_id = "cancel_scheduled_task"
    _scheduler: Optional[Any] = None

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="cancel_scheduled_task",
            description="Cancel a scheduled task.",
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "ID of the task to cancel.",
                    },
                },
                "required": ["task_id"],
            },
            category="scheduler",
        )

    def execute(self, **params: Any) -> ToolResult:
        if self._scheduler is None:
            return ToolResult(
                tool_name="cancel_scheduled_task",
                content="Scheduler not available.",
                success=False,
            )
        task_id = params.get("task_id", "")
        if not task_id:
            return ToolResult(
                tool_name="cancel_scheduled_task",
                content="Missing required parameter: task_id.",
                success=False,
            )
        try:
            self._scheduler.cancel_task(task_id)
            return ToolResult(
                tool_name="cancel_scheduled_task",
                content=f"Task {task_id} cancelled.",
                success=True,
            )
        except KeyError:
            return ToolResult(
                tool_name="cancel_scheduled_task",
                content=f"Task not found: {task_id}",
                success=False,
            )
        except Exception as exc:
            return ToolResult(
                tool_name="cancel_scheduled_task",
                content=f"Failed to cancel task: {exc}",
                success=False,
            )


__all__ = [
    "CancelScheduledTaskTool",
    "ListScheduledTasksTool",
    "PauseScheduledTaskTool",
    "ResumeScheduledTaskTool",
    "ScheduleTaskTool",
]
