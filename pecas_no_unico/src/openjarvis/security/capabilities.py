"""RBAC de capacidades em Python puro (sem Rust), negando por padrão.

Patches N12/N16: no upstream a checagem só existia no Rust, o padrão era
"liberar tudo" e a versão Python era código legado com semântica diferente.
Aqui:

- a decisão é toda Python e testada;
- o padrão é NEGAR (``default_deny=True``); liberar tudo exige pedir
  explicitamente com ``CapabilityPolicy.permissiva()``;
- negação explícita sempre vence;
- concessão com padrão de recurso (``pattern``) só vale quando o recurso casa.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Capability(str, Enum):
    """Rótulos de capacidade."""

    FILE_READ = "file:read"
    FILE_WRITE = "file:write"
    NETWORK_FETCH = "network:fetch"
    CODE_EXECUTE = "code:execute"
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    CHANNEL_SEND = "channel:send"
    TOOL_INVOKE = "tool:invoke"
    SCHEDULE_CREATE = "schedule:create"
    SYSTEM_ADMIN = "system:admin"


@dataclass(slots=True)
class CapabilityGrant:
    """Uma concessão de capacidade para um agente."""

    capability: str  # valor de Capability ou glob
    pattern: str = "*"  # glob do recurso (nome da ferramenta)


@dataclass(slots=True)
class AgentPolicy:
    """Política de um agente específico."""

    agent_id: str
    grants: List[CapabilityGrant] = field(default_factory=list)
    deny: List[str] = field(default_factory=list)  # negações explícitas


class CapabilityPolicy:
    """Política RBAC de capacidades para despacho de ferramentas.

    Regras de decisão (``check``):

    1. Escolhe a política: a do próprio agente; se ele não tiver, a do agente
       curinga ``_default``; se nenhuma existir, vale ``default_deny``.
    2. Qualquer ``deny`` que case com a capacidade nega, sempre.
    3. Qualquer concessão que case (capacidade e recurso) permite.
    4. Sem concessão que case: nega se ``default_deny``, senão permite.
    """

    _DEFAULT_AGENT = "_default"

    def __init__(
        self,
        *,
        policy_path: Optional[str] = None,
        default_deny: bool = True,
    ) -> None:
        self._policies: Dict[str, AgentPolicy] = {}
        self._default_deny = default_deny
        self._lock = threading.RLock()
        if policy_path:
            self._load_file(Path(policy_path))

    @classmethod
    def permissiva(cls) -> "CapabilityPolicy":
        """Política que libera tudo. Use só em testes/ambientes de confiança."""
        return cls(default_deny=False)

    def grant(self, agent_id: str, capability: str, pattern: str = "*") -> None:
        """Concede uma capacidade a um agente."""
        with self._lock:
            politica = self._policies.setdefault(
                agent_id, AgentPolicy(agent_id=agent_id)
            )
            politica.grants.append(
                CapabilityGrant(capability=capability, pattern=pattern)
            )

    def deny(self, agent_id: str, capability: str) -> None:
        """Nega explicitamente uma capacidade a um agente."""
        with self._lock:
            politica = self._policies.setdefault(
                agent_id, AgentPolicy(agent_id=agent_id)
            )
            politica.deny.append(capability)

    def check(self, agent_id: str, capability: str, resource: str = "") -> bool:
        """Diz se ``agent_id`` pode usar ``capability`` sobre ``resource``."""
        capability = getattr(capability, "value", capability)
        with self._lock:
            politica = self._policies.get(agent_id) if agent_id else None
            if politica is None:
                politica = self._policies.get(self._DEFAULT_AGENT)
            if politica is None:
                return not self._default_deny

            for negada in politica.deny:
                if fnmatch.fnmatchcase(capability, negada):
                    return False

            for concessao in politica.grants:
                if not fnmatch.fnmatchcase(capability, concessao.capability):
                    continue
                if concessao.pattern == "*":
                    return True
                if resource and fnmatch.fnmatchcase(resource, concessao.pattern):
                    return True

            return not self._default_deny

    def list_grants(self, agent_id: str) -> List[CapabilityGrant]:
        """Lista as concessões de um agente."""
        with self._lock:
            politica = self._policies.get(agent_id)
            return list(politica.grants) if politica else []

    def list_agents(self) -> List[str]:
        """Lista os agentes com política explícita."""
        with self._lock:
            return list(self._policies.keys())

    def _load_file(self, path: Path) -> None:
        """Carrega política de arquivo JSON, rejeitando dados incompletos."""
        dados = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(dados, dict) or not isinstance(dados.get("agents"), list):
            raise ValueError("Capability policy must contain an agents list")
        for agente in dados["agents"]:
            if not isinstance(agente, dict):
                raise ValueError("Capability policy agent must be an object")
            agent_id = agente.get("agent_id")
            if not isinstance(agent_id, str) or not agent_id.strip():
                raise ValueError("Capability policy agent_id must be a nonempty string")
            concessoes = agente.get("grants", [])
            negadas = agente.get("deny", [])
            if not isinstance(concessoes, list) or not isinstance(negadas, list):
                raise ValueError("Capability policy grants and deny must be lists")
            for g in concessoes:
                if (
                    not isinstance(g, dict)
                    or not isinstance(g.get("capability"), str)
                    or not g["capability"].strip()
                    or not isinstance(g.get("pattern", "*"), str)
                ):
                    raise ValueError(
                        "Capability policy grant must specify a capability"
                    )
            if any(not isinstance(c, str) or not c.strip() for c in negadas):
                raise ValueError("Capability policy deny entries must be strings")

        for agente in dados["agents"]:
            agent_id = agente["agent_id"]
            with self._lock:
                # Política explícita vazia continua sendo política do agente:
                # ela não herda as concessões do curinga.
                self._policies.setdefault(agent_id, AgentPolicy(agent_id=agent_id))
            for g in agente.get("grants", []):
                self.grant(agent_id, g["capability"], g.get("pattern", "*"))
            for negada in agente.get("deny", []):
                self.deny(agent_id, negada)

    def save(self, path: Path) -> None:
        """Salva a política em JSON."""
        with self._lock:
            agentes = [
                {
                    "agent_id": agent_id,
                    "grants": [
                        {"capability": g.capability, "pattern": g.pattern}
                        for g in politica.grants
                    ],
                    "deny": list(politica.deny),
                }
                for agent_id, politica in self._policies.items()
            ]
        path.write_text(json.dumps({"agents": agentes}, indent=2), encoding="utf-8")


# Canonical capability requirements for every in-tree tool.  This table is a
# security floor: ToolSpec declarations may add requirements, but they may not
# weaken these.  Keep explicitly-safe tools in the table with an empty list so
# an omitted future built-in can be distinguished from a reviewed safe one.
DEFAULT_TOOL_CAPABILITIES: Dict[str, List[str]] = {
    "agent_kill": [Capability.SYSTEM_ADMIN],
    "agent_list": [Capability.SYSTEM_ADMIN],
    "agent_send": [Capability.SYSTEM_ADMIN],
    "agent_spawn": [Capability.SYSTEM_ADMIN],
    "apply_patch": [Capability.FILE_WRITE],
    "audio_transcribe": [Capability.FILE_READ, Capability.NETWORK_FETCH],
    "browser_axtree": [Capability.NETWORK_FETCH],
    "browser_click": [Capability.NETWORK_FETCH],
    "browser_extract": [Capability.NETWORK_FETCH],
    "browser_navigate": [Capability.NETWORK_FETCH],
    "browser_screenshot": [Capability.NETWORK_FETCH],
    "browser_type": [Capability.NETWORK_FETCH],
    "calculator": [],
    "calendar_search": [Capability.FILE_READ],
    "calendar_upcoming": [Capability.FILE_READ],
    "cancel_scheduled_task": [Capability.SCHEDULE_CREATE],
    "channel_list": [Capability.SYSTEM_ADMIN],
    "channel_send": [Capability.CHANNEL_SEND],
    "channel_status": [Capability.SYSTEM_ADMIN],
    "check_permission": [Capability.MEMORY_READ],
    "code_interpreter": [Capability.CODE_EXECUTE],
    "code_interpreter_docker": [Capability.CODE_EXECUTE],
    "db_query": [Capability.CODE_EXECUTE],
    "digest_collect": [Capability.MEMORY_READ, Capability.NETWORK_FETCH],
    "docker_shell_exec": [Capability.CODE_EXECUTE],
    "execute_pending_actions": [
        Capability.SYSTEM_ADMIN,
        Capability.CHANNEL_SEND,
        Capability.NETWORK_FETCH,
    ],
    "file_read": [Capability.FILE_READ],
    "file_write": [Capability.FILE_WRITE],
    "get_pending_actions": [Capability.MEMORY_READ],
    "fx_macro_data": [Capability.NETWORK_FETCH],
    "get_weather": [Capability.NETWORK_FETCH],
    "git_commit": [Capability.FILE_WRITE],
    "git_diff": [Capability.FILE_READ],
    "git_log": [Capability.FILE_READ],
    "git_status": [Capability.FILE_READ],
    "http_request": [Capability.NETWORK_FETCH],
    "image_generate": [Capability.NETWORK_FETCH, Capability.FILE_WRITE],
    "kg_add_entity": [Capability.MEMORY_WRITE],
    "kg_add_relation": [Capability.MEMORY_WRITE],
    "kg_neighbors": [Capability.MEMORY_READ],
    "kg_query": [Capability.MEMORY_READ],
    "knowledge_search": [Capability.MEMORY_READ],
    "knowledge_sql": [Capability.MEMORY_READ],
    "list_scheduled_tasks": [Capability.SCHEDULE_CREATE],
    "llm": [Capability.NETWORK_FETCH],
    "memory_index": [Capability.MEMORY_WRITE],
    "memory_manage": [Capability.MEMORY_READ, Capability.MEMORY_WRITE],
    "memory_retrieve": [Capability.MEMORY_READ],
    "memory_search": [Capability.MEMORY_READ],
    "memory_store": [Capability.MEMORY_WRITE],
    "pause_scheduled_task": [Capability.SCHEDULE_CREATE],
    "pdf_extract": [Capability.FILE_READ],
    "queue_action": [Capability.MEMORY_WRITE],
    "record_decision": [Capability.SYSTEM_ADMIN, Capability.MEMORY_WRITE],
    "repl": [Capability.CODE_EXECUTE],
    "resume_scheduled_task": [Capability.SCHEDULE_CREATE],
    "retrieval": [Capability.MEMORY_READ],
    "scan_chunks": [Capability.MEMORY_READ],
    "schedule_task": [Capability.SCHEDULE_CREATE],
    "shell_exec": [Capability.CODE_EXECUTE],
    "skill_manage": [Capability.FILE_READ, Capability.FILE_WRITE],
    "text_to_speech": [Capability.NETWORK_FETCH, Capability.FILE_WRITE],
    "think": [],
    "user_profile_manage": [Capability.FILE_READ, Capability.FILE_WRITE],
    "web_search": [Capability.NETWORK_FETCH],
}

_SAFE_BUILTIN_PROVENANCE = {
    "calculator": ("openjarvis.tools.calculator", "CalculatorTool"),
    "think": ("openjarvis.tools.think", "ThinkTool"),
}


def canonical_tool_capabilities(tool: Any) -> List[str]:
    """Return the non-bypassable capability floor for *tool*.

    Third-party tools remain governed by their ToolSpec.  An in-tree tool that
    was newly registered without being inventoried fails closed as
    ``system:admin`` instead of silently becoming unrestricted.
    """
    module = type(tool).__module__
    name = tool.spec.name
    is_builtin = (
        module == "openjarvis.tools"
        or module.startswith("openjarvis.tools.")
        or module == "openjarvis.scheduler.tools"
    )
    if module == "openjarvis.tools.mcp_adapter":
        # MCP tool names are remote-controlled.  Resolve adapter provenance
        # before the name table so a server cannot impersonate a reviewed-safe
        # local tool such as ``calculator`` or ``think``.
        return [Capability.TOOL_INVOKE]
    if is_builtin:
        if name in DEFAULT_TOOL_CAPABILITIES:
            canonical = list(DEFAULT_TOOL_CAPABILITIES[name])
            expected = _SAFE_BUILTIN_PROVENANCE.get(name)
            if (
                expected is not None
                and (
                    module,
                    type(tool).__name__,
                )
                != expected
            ):
                logger.error(
                    "Tool %r claimed reviewed-safe built-in provenance from %s.%s",
                    name,
                    module,
                    type(tool).__name__,
                )
                return [Capability.SYSTEM_ADMIN]
            return canonical
        logger.error("Built-in tool %r has no canonical capability inventory", name)
        return [Capability.SYSTEM_ADMIN]
    if name in DEFAULT_TOOL_CAPABILITIES:
        canonical = list(DEFAULT_TOOL_CAPABILITIES[name])
        # Third-party tools that collide with a privileged name retain its
        # security floor.  Reviewed-safe names are safe only for their in-tree
        # implementation and therefore fail closed on foreign provenance.
        return canonical or [Capability.SYSTEM_ADMIN]
    return []


__all__ = [
    "AgentPolicy",
    "Capability",
    "CapabilityGrant",
    "CapabilityPolicy",
    "canonical_tool_capabilities",
    "DEFAULT_TOOL_CAPABILITIES",
]
