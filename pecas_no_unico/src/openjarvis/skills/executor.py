"""SkillExecutor — runs skill steps sequentially through ToolExecutor."""

from __future__ import annotations

import contextvars
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from openjarvis.core.events import EventBus, EventType
from openjarvis.core.types import ToolCall, ToolResult
from openjarvis.skills.security import validate_capabilities
from openjarvis.skills.types import SkillManifest
from openjarvis.tools._stubs import ToolExecutor


@dataclass(slots=True)
class SkillResult:
    skill_name: str = ""
    success: bool = True
    step_results: List[ToolResult] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)


# Profundidade de sub-skills em execução (por contexto/thread).
# Patch N2/N6: o upstream não limitava a recursão de ``skill_name`` em tempo de
# execução (só o grafo estático de dependências).
MAX_PROFUNDIDADE = 5
_profundidade: contextvars.ContextVar[int] = contextvars.ContextVar(
    "openjarvis_skill_profundidade", default=0
)


class TemplateError(ValueError):
    """O ``arguments_template`` não é um JSON válido com marcadores em strings."""


# Resolver callback: given a skill name and the current context, returns a SkillResult.
SkillResolver = Callable[[str, Dict[str, Any]], SkillResult]


class SkillExecutor:
    """Execute a skill manifest step-by-step.

    Each step's arguments_template supports ``{key}`` placeholders
    that are resolved from the context dict (populated by prior step outputs).
    """

    def __init__(
        self,
        tool_executor: ToolExecutor,
        *,
        bus: Optional[EventBus] = None,
        allowed_capabilities: Optional[Set[str]] = frozenset(),  # type: ignore[assignment]
    ) -> None:
        self._tool_executor = tool_executor
        self._bus = bus
        self._skill_resolver: Optional[SkillResolver] = None
        # Patch N4: o padrão agora IMPÕE (conjunto vazio): skill que declara
        # capacidades fora do conjunto é bloqueada antes de qualquer passo.
        # ``None`` desliga a imposição (só para testes/ambientes de confiança).
        self._allowed_capabilities: Optional[Set[str]] = allowed_capabilities

    def set_skill_resolver(self, resolver: SkillResolver) -> None:
        """Register a callback used to delegate ``skill_name`` steps."""
        self._skill_resolver = resolver

    def run(
        self,
        manifest: SkillManifest,
        *,
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        """Execute all steps in a skill manifest."""
        nivel = _profundidade.get()
        if nivel >= MAX_PROFUNDIDADE:
            return SkillResult(
                skill_name=manifest.name,
                success=False,
                step_results=[
                    ToolResult(
                        tool_name=manifest.name,
                        content=(
                            f"Blocked: skill '{manifest.name}' excede a profundidade "
                            f"máxima de sub-skills ({MAX_PROFUNDIDADE})."
                        ),
                        success=False,
                    )
                ],
                context=dict(initial_context or {}),
            )
        token = _profundidade.set(nivel + 1)
        try:
            return self._executar(manifest, initial_context)
        finally:
            _profundidade.reset(token)

    def _executar(
        self,
        manifest: SkillManifest,
        initial_context: Optional[Dict[str, Any]],
    ) -> SkillResult:
        missing = (
            validate_capabilities(manifest, self._allowed_capabilities)
            if self._allowed_capabilities is not None
            else []
        )
        if missing:
            if self._bus:
                self._bus.publish(
                    EventType.SKILL_EXECUTE_START,
                    {"skill": manifest.name, "steps": len(manifest.steps)},
                )
                self._bus.publish(
                    EventType.SKILL_EXECUTE_END,
                    {"skill": manifest.name, "success": False},
                )
            return SkillResult(
                skill_name=manifest.name,
                success=False,
                step_results=[
                    ToolResult(
                        tool_name=manifest.name,
                        content=(
                            f"Blocked: skill '{manifest.name}' requires "
                            f"capabilities {missing} that were not granted "
                            "for this session."
                        ),
                        success=False,
                    )
                ],
                context=dict(initial_context or {}),
            )

        ctx: Dict[str, Any] = dict(initial_context or {})
        all_results: List[ToolResult] = []

        if self._bus:
            self._bus.publish(
                EventType.SKILL_EXECUTE_START,
                {"skill": manifest.name, "steps": len(manifest.steps)},
            )

        for i, step in enumerate(manifest.steps):
            step_id = step.tool_name or step.skill_name

            # Render template
            try:
                rendered = self._render_template(step.arguments_template, ctx)
            except Exception as exc:
                result = ToolResult(
                    tool_name=step_id,
                    content=f"Template rendering error: {exc}",
                    success=False,
                )
                all_results.append(result)
                break

            if step.skill_name:
                # Delegate to sub-skill resolver
                result = self._run_sub_skill(
                    step.skill_name, rendered, ctx, manifest.name, i
                )
            else:
                # Execute via tool executor
                tool_call = ToolCall(
                    id=f"skill_{manifest.name}_{i}",
                    name=step.tool_name,
                    arguments=rendered,
                )
                result = self._tool_executor.execute(tool_call)

            all_results.append(result)

            if not result.success:
                break

            # Store output in context
            if step.output_key:
                ctx[step.output_key] = result.content

        success = all(r.success for r in all_results)

        if self._bus:
            self._bus.publish(
                EventType.SKILL_EXECUTE_END,
                {"skill": manifest.name, "success": success},
            )

        return SkillResult(
            skill_name=manifest.name,
            success=success,
            step_results=all_results,
            context=ctx,
        )

    def _run_sub_skill(
        self,
        skill_name: str,
        rendered_args: str,
        parent_ctx: Dict[str, Any],
        parent_skill: str,
        step_index: int,
    ) -> ToolResult:
        """Invoke the skill resolver and convert its result to a ToolResult."""
        if self._skill_resolver is None:
            return ToolResult(
                tool_name=skill_name,
                content=f"No skill resolver registered for sub-skill '{skill_name}'",
                success=False,
            )

        # Parse rendered args and merge into a copy of the parent context
        try:
            args: Dict[str, Any] = json.loads(rendered_args)
        except json.JSONDecodeError:
            args = {}
        if not isinstance(args, dict):
            args = {}

        child_ctx = {**parent_ctx, **args}

        sub_result: SkillResult = self._skill_resolver(skill_name, child_ctx)

        # Expose the final context value under the first output_key, or the
        # last step's content, as the synthetic "content" of this ToolResult.
        content: Any = ""
        if sub_result.context:
            # Return the last stored value from the child's context that is
            # not already in the parent context (i.e. the output of the sub-skill).
            new_keys = [k for k in sub_result.context if k not in parent_ctx]
            if new_keys:
                content = sub_result.context[new_keys[-1]]
            else:
                content = (
                    list(sub_result.context.values())[-1] if sub_result.context else ""
                )
        elif sub_result.step_results:
            content = sub_result.step_results[-1].content

        return ToolResult(
            tool_name=skill_name,
            content=content,
            success=sub_result.success,
        )

    @staticmethod
    def _render_template(template: str, ctx: Dict[str, Any]) -> str:
        """Renderiza o template de forma ESTRUTURAL (a prova de injeção de JSON).

        Patch N2: o upstream trocava ``{chave}`` por texto cru dentro do texto
        JSON; um valor com aspas (parâmetro do modelo ou SAÍDA de um passo
        anterior, ou seja, conteúdo web/arquivo) fechava o campo e acrescentava
        outros. Aqui o template é lido como JSON e a troca acontece só dentro
        das STRINGS já decodificadas; o resultado é serializado de novo.
        Se a string inteira é um único marcador e o valor não é texto, o tipo
        original é preservado.

        O template precisa ser JSON válido (marcadores só dentro de strings);
        caso contrário levanta ``TemplateError``. Marcadores sem valor no
        contexto ficam literais, como no upstream.
        """
        try:
            alvo = json.loads(template)
        except json.JSONDecodeError as exc:
            raise TemplateError(f"Template não é JSON válido: {exc.msg}") from exc

        marcador = re.compile(r"\{(\w+)\}")

        def _valor_texto(valor: Any) -> str:
            return valor if isinstance(valor, str) else json.dumps(valor)

        def _trocar(no: Any) -> Any:
            if isinstance(no, str):
                inteiro = marcador.fullmatch(no)
                if inteiro and inteiro.group(1) in ctx:
                    return ctx[inteiro.group(1)]
                return marcador.sub(
                    lambda m: (
                        _valor_texto(ctx[m.group(1)])
                        if m.group(1) in ctx
                        else m.group(0)
                    ),
                    no,
                )
            if isinstance(no, list):
                return [_trocar(x) for x in no]
            if isinstance(no, dict):
                return {k: _trocar(v) for k, v in no.items()}
            return no

        return json.dumps(_trocar(alvo), ensure_ascii=False)


__all__ = [
    "MAX_PROFUNDIDADE",
    "SkillExecutor",
    "SkillResolver",
    "SkillResult",
    "TemplateError",
]
