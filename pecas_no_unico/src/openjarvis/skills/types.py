"""Skill type definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(slots=True)
class SkillStep:
    """A single step in a skill pipeline."""

    tool_name: str = ""
    skill_name: str = ""  # invoke another skill instead of a tool
    arguments_template: str = "{}"  # Jinja2-style template
    output_key: str = ""  # Key to store result in context


@dataclass(slots=True)
class SkillManifest:
    """Manifest describing a reusable skill."""

    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    steps: List[SkillStep] = field(default_factory=list)
    required_capabilities: List[str] = field(default_factory=list)
    signature: str = ""  # Base64-encoded Ed25519 signature
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    depends: List[str] = field(default_factory=list)
    user_invocable: bool = True
    disable_model_invocation: bool = False
    markdown_content: str = ""  # loaded from SKILL.md

    def manifest_bytes(self) -> bytes:
        """Serializa o manifesto (sem a assinatura) para assinar/verificar.

        Patch N1: o upstream NÃO assinava ``markdown_content`` (o corpo do
        SKILL.md, que vira instrução para o modelo), nem ``metadata``,
        ``user_invocable`` e ``disable_model_invocation``. Quem alterasse o
        corpo mantinha a assinatura válida. A versão 2 cobre tudo isso.
        """
        import json

        data = {
            "signature_version": 2,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "steps": [
                {
                    "tool_name": s.tool_name,
                    "skill_name": s.skill_name,
                    "arguments_template": s.arguments_template,
                    "output_key": s.output_key,
                }
                for s in self.steps
            ],
            "required_capabilities": self.required_capabilities,
            "tags": self.tags,
            "depends": self.depends,
            "metadata": self.metadata,
            "user_invocable": self.user_invocable,
            "disable_model_invocation": self.disable_model_invocation,
            "markdown_content": self.markdown_content,
        }
        return json.dumps(data, sort_keys=True, default=str).encode("utf-8")


__all__ = ["SkillManifest", "SkillStep"]
