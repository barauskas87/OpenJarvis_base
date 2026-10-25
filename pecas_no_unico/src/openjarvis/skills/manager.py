"""Gerenciador de skills: descoberta, catálogo, ferramentas e execução.

Patches N1, N4, N6. Diferenças em relação ao upstream:

- N4: os três ``SkillExecutor`` recebem ``allowed_capabilities`` (o upstream
  nunca passava, então nenhuma imposição acontecia); a checagem usa a UNIÃO
  transitiva de capacidades da skill e de suas dependências;
- N6: ``DepthExceededError`` remove só as skills que estouram o limite, em vez
  de abortar a descoberta inteira;
- N1: ``discover`` repassa verificação de assinatura e scanner de injeção;
- removidos ``discover_from_traces`` (escrevia TOML com nome de ferramenta
  sem escape e dependia do módulo ``learning``) e ``find_installed_paths`` /
  ``remove`` (apagavam diretórios por casamento de nome em ``./skills``);
- o diretório de overlay não vem mais de ``load_config()``.
"""

from __future__ import annotations

import html
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from openjarvis.core.events import EventBus
from openjarvis.core.paths import get_config_dir
from openjarvis.skills.dependency import (
    DependencyCycleError,
    DepthExceededError,
    compute_capability_union,
    validate_dependencies,
)
from openjarvis.skills.executor import SkillExecutor, SkillResult
from openjarvis.skills.loader import discover_skills
from openjarvis.skills.tool_adapter import SkillTool
from openjarvis.skills.types import SkillManifest
from openjarvis.tools._stubs import BaseTool, ToolExecutor

logger = logging.getLogger(__name__)


class SkillManager:
    """Coordena descoberta, resolução, catálogo e execução de skills."""

    def __init__(
        self,
        bus: EventBus,
        *,
        capability_policy: Optional[Any] = None,
        overlay_dir: Optional[Path] = None,
        allowed_capabilities: Optional[Iterable[str]] = None,
    ) -> None:
        self._bus = bus
        self._capability_policy = capability_policy
        self._skills: Dict[str, SkillManifest] = {}
        self._tool_executor: Optional[ToolExecutor] = None
        # Capacidades que o operador concede às skills. Vazio = skill que
        # declara qualquer capacidade é bloqueada. Veja ``permitir``.
        self._allowed_capabilities: Set[str] = set(allowed_capabilities or ())
        if overlay_dir is None:
            overlay_dir = get_config_dir() / "learning" / "skills"
        self._overlay_dir = Path(overlay_dir).expanduser()

    # ------------------------------------------------------------------
    # Capacidades
    # ------------------------------------------------------------------

    def permitir(self, *capacidades: str) -> None:
        """Concede capacidades às skills (ex.: ``"network:fetch"``)."""
        self._allowed_capabilities.update(capacidades)

    def _capacidades_faltando(self, nome: str) -> List[str]:
        """Capacidades exigidas (transitivamente) e não concedidas."""
        exigidas = compute_capability_union(nome, self._skills)
        return [c for c in exigidas if c not in self._allowed_capabilities]

    # ------------------------------------------------------------------
    # Descoberta
    # ------------------------------------------------------------------

    def discover(
        self,
        paths: Optional[List[Path]] = None,
        *,
        verify_signature: bool = False,
        public_key: Optional[bytes] = None,
        scan_for_injection: bool = False,
    ) -> None:
        """Varre diretórios na ordem e registra as skills (a primeira vence)."""
        if paths:
            for diretorio in paths:
                manifestos = discover_skills(
                    diretorio,
                    verify_signature=verify_signature,
                    public_key=public_key,
                    scan_for_injection=scan_for_injection,
                )
                for manifesto in manifestos:
                    if manifesto.name not in self._skills:
                        self._skills[manifesto.name] = manifesto
            if self._skills:
                self._prune_dependency_cycles()
        self._load_overlays()

    def _prune_dependency_cycles(self) -> None:
        """Remove skills em ciclo ou além da profundidade máxima, e revalida."""
        while self._skills:
            try:
                validate_dependencies(self._skills)
                return
            except (DependencyCycleError, DepthExceededError) as exc:
                if not exc.skills:
                    return
                motivo = (
                    "ciclo de dependência"
                    if isinstance(exc, DependencyCycleError)
                    else "profundidade de dependência excedida"
                )
                for nome in sorted(exc.skills):
                    logger.warning("Skill '%s' removida: %s", nome, motivo)
                    self._skills.pop(nome, None)

    def _load_overlays(self) -> None:
        """Aplica overlays de otimização (descrição e exemplos)."""
        from openjarvis.skills.overlay import SkillOverlayLoader

        carregador = SkillOverlayLoader(self._overlay_dir)
        for nome, manifesto in self._skills.items():
            overlay = carregador.load(nome)
            if overlay is None:
                continue
            if overlay.description:
                manifesto.description = overlay.description
            if overlay.few_shot:
                metadata = dict(manifesto.metadata) if manifesto.metadata else {}
                oj = dict(metadata.get("openjarvis", {}) or {})
                oj["few_shot"] = list(overlay.few_shot)
                metadata["openjarvis"] = oj
                manifesto.metadata = metadata

    # ------------------------------------------------------------------
    # Resolução
    # ------------------------------------------------------------------

    def resolve(self, name: str) -> SkillManifest:
        """Devolve o manifesto de uma skill; ``KeyError`` se não existir."""
        if name not in self._skills:
            raise KeyError(f"Skill '{name}' not found")
        return self._skills[name]

    def skill_names(self) -> List[str]:
        """Nomes das skills registradas."""
        return list(self._skills.keys())

    # ------------------------------------------------------------------
    # Ferramentas
    # ------------------------------------------------------------------

    def _novo_executor(self, executor: Optional[ToolExecutor]) -> SkillExecutor:
        skill_exec = SkillExecutor(
            executor or _NullToolExecutor(),
            bus=self._bus,
            allowed_capabilities=self._todas_permitidas(),
        )
        skill_exec.set_skill_resolver(self._make_resolver())
        return skill_exec

    def _todas_permitidas(self) -> Set[str]:
        """Conjunto vivo: concessões feitas depois de criar o executor valem."""
        return self._allowed_capabilities

    def get_skill_tools(
        self, *, tool_executor: Optional[ToolExecutor] = None
    ) -> List[BaseTool]:
        """Envolve cada skill registrada em um ``SkillTool``."""
        executor = tool_executor or self._tool_executor
        ferramentas: List[BaseTool] = []
        for manifesto in self._skills.values():
            if manifesto.disable_model_invocation:
                continue
            skill_exec = self._novo_executor(executor)
            ferramentas.append(SkillTool(manifesto, skill_exec, skill_manager=self))
        return ferramentas

    def _make_resolver(self):
        """Callback que delega a execução de sub-skills (com a mesma imposição)."""

        def _resolver(name: str, context: Dict[str, Any]) -> SkillResult:
            manifesto = self.resolve(name)
            skill_exec = self._novo_executor(self._tool_executor)
            return skill_exec.run(manifesto, initial_context=context)

        return _resolver

    # ------------------------------------------------------------------
    # Catálogo
    # ------------------------------------------------------------------

    def get_catalog_xml(self) -> str:
        """Catálogo ``<available_skills>`` (sem skills ocultas ao modelo)."""
        linhas: List[str] = ["<available_skills>"]
        for manifesto in self._skills.values():
            if manifesto.disable_model_invocation:
                continue
            nome = html.escape(manifesto.name)
            descricao = html.escape(manifesto.description or manifesto.name)
            linhas.append(f"  <skill name={nome!r} description={descricao!r} />")
        linhas.append("</available_skills>")
        return "\n".join(linhas)

    def get_few_shot_examples(self) -> List[str]:
        """Exemplos few-shot formatados para o prompt do sistema."""
        exemplos: List[str] = []
        for nome, manifesto in self._skills.items():
            if manifesto.disable_model_invocation:
                continue
            oj = manifesto.metadata.get("openjarvis", {}) if manifesto.metadata else {}
            for ex in oj.get("few_shot", []) or []:
                if not isinstance(ex, dict):
                    continue
                entrada, saida = str(ex.get("input", "")), str(ex.get("output", ""))
                if entrada or saida:
                    exemplos.append(f"### {nome}\nInput: {entrada}\nOutput: {saida}")
        return exemplos

    # ------------------------------------------------------------------
    # Execução
    # ------------------------------------------------------------------

    def execute(
        self,
        name: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        """Resolve e executa uma skill pelo nome."""
        manifesto = self.resolve(name)
        faltando = self._capacidades_faltando(name)
        if faltando:
            from openjarvis.core.types import ToolResult

            return SkillResult(
                skill_name=name,
                success=False,
                step_results=[
                    ToolResult(
                        tool_name=name,
                        content=(
                            f"Blocked: skill '{name}' (ou dependência) exige "
                            f"capacidades não concedidas: {faltando}."
                        ),
                        success=False,
                    )
                ],
                context=dict(context or {}),
            )
        return self._novo_executor(self._tool_executor).run(
            manifesto, initial_context=context
        )

    def set_tool_executor(self, tool_executor: ToolExecutor) -> None:
        """Define o ``ToolExecutor`` usado nos passos das skills."""
        self._tool_executor = tool_executor


class _NullToolExecutor(ToolExecutor):
    """Executor vazio: qualquer ferramenta vira um erro, nunca uma exceção."""

    def __init__(self) -> None:
        super().__init__(tools=[], bus=None)


__all__ = ["SkillManager"]
