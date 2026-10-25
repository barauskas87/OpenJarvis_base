"""Agent loop guard — detect and prevent degenerate tool-calling loops."""

from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass
from typing import Optional

from openjarvis.core.events import EventBus, EventType


@dataclass(slots=True)
class LoopGuardConfig:
    """Configuration for the loop guard."""

    enabled: bool = True
    max_identical_calls: int = 3  # SHA-256 of (tool_name, arguments)
    ping_pong_window: int = 6  # detect A-B-A-B cycling
    poll_tool_budget: int = 5  # max calls to same polling tool
    max_context_messages: int = 100  # context overflow threshold
    warn_before_block: bool = True  # warn on first cycle, block on second
    # Patch N13: orçamento de chamadas só vale para ferramentas de polling.
    # No upstream o orçamento (5) valia para TODA ferramenta e bloqueava, por
    # exemplo, a 6ª busca web de uma execução normal.
    poll_tools: frozenset = frozenset()


@dataclass(slots=True)
class LoopVerdict:
    """Result of a loop guard check."""

    blocked: bool = False
    reason: str = ""
    warned: bool = False
    # Patch N13b: tipo do ciclo ("identical_call", "poll_budget", "ping_pong").
    # O upstream usava o TEXTO do motivo como chave do aviso; como o texto
    # trazia o contador ("repetida 4 vezes"), a chave mudava a cada chamada e
    # o bloqueio nunca chegava (sempre "só aviso").
    kind: str = ""
    tool: str = ""


class LoopGuard:
    """Detect and prevent degenerate agent loops.

    Features:
    1. Hash tracking: SHA-256 of (tool_name, args) blocks after max_identical_calls
    2. Ping-pong detection: Sliding window detects A-B-A-B or A-B-C-A-B-C patterns
    3. Poll-tool awareness: Tools with spec.metadata["polling"] = True
       get relaxed budget
    4. Context overflow recovery: 4-stage compression of message history
    """

    def __init__(self, config: LoopGuardConfig, *, bus: Optional[EventBus] = None):
        self._config = config
        self._bus = bus
        # Track call hashes and their counts
        self._call_counts: dict[str, int] = {}
        # Track tool name sequence for pattern detection
        self._tool_sequence: deque[str] = deque(maxlen=config.ping_pong_window * 2)
        # Track per-tool call counts (for polling budget)
        self._per_tool_counts: dict[str, int] = {}
        # Track cycle keys that have already been warned (for warn-before-block)
        self._warned_cycles: set[str] = set()

    def check_call(self, tool_name: str, arguments: str) -> LoopVerdict:
        """Diz se uma chamada de ferramenta pode seguir ou deve ser bloqueada."""
        verdict = self._python_check(tool_name, arguments)

        # Aviso antes do bloqueio: o primeiro ciclo de cada (tipo, ferramenta)
        # só avisa; a repetição bloqueia.
        if verdict.blocked and self._config.warn_before_block:
            chave = f"{verdict.kind}:{verdict.tool}"
            if chave not in self._warned_cycles:
                self._warned_cycles.add(chave)
                return LoopVerdict(
                    blocked=False,
                    warned=True,
                    reason=verdict.reason,
                    kind=verdict.kind,
                    tool=verdict.tool,
                )
        return verdict

    def _python_check(self, tool_name: str, arguments: str) -> LoopVerdict:
        """Detecção de laços (somente Python)."""
        # 1. Hash tracking — identical calls
        call_hash = hashlib.sha256(f"{tool_name}:{arguments}".encode()).hexdigest()[:16]
        self._call_counts[call_hash] = self._call_counts.get(call_hash, 0) + 1
        if self._call_counts[call_hash] > self._config.max_identical_calls:
            self._emit_triggered("identical_call", tool_name)
            return LoopVerdict(
                blocked=True,
                reason=(
                    f"Identical call to '{tool_name}' repeated "
                    f"{self._call_counts[call_hash]} times "
                    f"(max {self._config.max_identical_calls})."
                ),
                kind="identical_call",
                tool=tool_name,
            )

        # 2. Per-tool budget (polling tools)
        if tool_name in self._config.poll_tools:
            self._per_tool_counts[tool_name] = (
                self._per_tool_counts.get(tool_name, 0) + 1
            )
            if self._per_tool_counts[tool_name] > self._config.poll_tool_budget:
                self._emit_triggered("poll_budget", tool_name)
                return LoopVerdict(
                    blocked=True,
                    reason=(
                        f"Tool '{tool_name}' exceeded poll budget "
                        f"({self._config.poll_tool_budget})."
                    ),
                    kind="poll_budget",
                    tool=tool_name,
                )

        # 3. Ping-pong detection
        # Patch N13c: o ciclo é detectado sobre a ASSINATURA da chamada
        # (ferramenta + argumentos), não só sobre o nome. No upstream, seis
        # chamadas seguidas à mesma ferramenta com argumentos diferentes
        # (ex.: seis buscas) eram "ping-pong" e bloqueadas.
        self._tool_sequence.append(call_hash)
        if len(self._tool_sequence) >= self._config.ping_pong_window:
            if self._detect_ping_pong():
                self._emit_triggered("ping_pong", tool_name)
                return LoopVerdict(
                    blocked=True,
                    reason="Repetitive tool-calling pattern detected (ping-pong).",
                    kind="ping_pong",
                    tool=tool_name,
                )

        return LoopVerdict()

    def check_response(self, content: str) -> LoopVerdict:
        """Check whether an agent response indicates a loop. Reserved for future use."""
        return LoopVerdict()

    @staticmethod
    def _is_system(msg: object) -> bool:
        """Check if a message has role == system."""
        return getattr(msg, "role", None) == "system"

    @staticmethod
    def _is_tool(msg: object) -> bool:
        """Check if a message has role == tool."""
        return getattr(msg, "role", None) == "tool"

    def compress_context(self, messages: list) -> list:
        """Apply 4-stage context overflow recovery to message list.

        Stages:
        1. Summarize old tool results (replace content with "[Tool result truncated]")
        2. Sliding window — keep only recent messages
        3. Drop tool call/result pairs from the middle
        4. Truncate to system + last 2 exchanges
        """
        if len(messages) <= self._config.max_context_messages:
            return messages

        # Stage 1: Truncate old tool result messages
        threshold = len(messages) // 2
        compressed = []
        for i, msg in enumerate(messages):
            if i < threshold and self._is_tool(msg):
                from openjarvis.core.types import Message, Role

                compressed.append(
                    Message(
                        role=Role.TOOL,
                        content="[Tool result truncated]",
                        tool_call_id=getattr(
                            msg,
                            "tool_call_id",
                            None,
                        ),
                        name=getattr(msg, "name", None),
                    )
                )
            else:
                compressed.append(msg)

        if len(compressed) <= self._config.max_context_messages:
            return compressed

        # Stage 2: Sliding window — keep system + recent
        system_msgs = [m for m in compressed if self._is_system(m)]
        non_system = [m for m in compressed if not self._is_system(m)]
        window_size = self._config.max_context_messages - len(system_msgs)
        if len(non_system) > window_size:
            non_system = non_system[-window_size:]
        compressed = system_msgs + non_system

        if len(compressed) <= self._config.max_context_messages:
            return compressed

        # Stage 3: Drop tool call/result pairs from middle
        keep_start = max(
            len(system_msgs),
            len(compressed) // 10,
        )
        keep_end = len(compressed) // 2
        compressed = compressed[:keep_start] + compressed[-keep_end:]

        if len(compressed) <= self._config.max_context_messages:
            return compressed

        # Stage 4: Extreme — system + last 2 exchanges
        sys_final = [m for m in compressed if self._is_system(m)]
        tail = [m for m in compressed if not self._is_system(m)]
        return sys_final + tail[-4:]

    def reset(self) -> None:
        """Zera todo o estado de rastreamento."""
        self._call_counts.clear()
        self._tool_sequence.clear()
        self._per_tool_counts.clear()
        self._warned_cycles.clear()

    def _detect_ping_pong(self) -> bool:
        """Detect repeating patterns in tool call sequence."""
        seq = list(self._tool_sequence)
        n = len(seq)
        # Check for period-2 pattern (A-B-A-B)
        for period in (2, 3):
            if n >= period * 2:
                tail = seq[-period * 2 :]
                pattern = tail[:period]
                if len(set(pattern)) < 2:
                    continue  # repetição de uma só chamada é outro detector
                if all(tail[i] == pattern[i % period] for i in range(len(tail))):
                    return True
        return False

    def _emit_triggered(self, reason_type: str, tool_name: str) -> None:
        """Publish a LOOP_GUARD_TRIGGERED event."""
        if self._bus:
            self._bus.publish(
                EventType.LOOP_GUARD_TRIGGERED,
                {"reason_type": reason_type, "tool": tool_name},
            )


__all__ = ["LoopGuard", "LoopGuardConfig", "LoopVerdict"]
