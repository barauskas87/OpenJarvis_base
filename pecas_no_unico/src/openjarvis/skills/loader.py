"""Carregador de skills (TOML e SKILL.md) com verificação que falha FECHADA.

Patches N1 e N5. Diferenças em relação ao upstream:

- N1: ``verify_signature=True`` agora EXIGE chave pública e assinatura. No
  upstream (``if verify_signature and public_key and manifest.signature``) uma
  skill sem assinatura, ou uma chamada sem chave, passava sem nenhum erro;
- N1: a assinatura cobre também o corpo do SKILL.md e os metadados
  (ver ``SkillManifest.manifest_bytes``), e é verificada DEPOIS de juntar
  TOML + SKILL.md;
- N1: ``discover_skills`` aceita os mesmos parâmetros de verificação (o
  upstream nunca verificava no caminho de descoberta);
- N1: ``scan_for_injection`` usa o ``InjectionScanner`` sobre descrição, passos
  e corpo (o upstream usava o detector de SEGREDOS e ignorava o corpo);
- sem o "fallback legado" que aceitava nome inválido quando a validação estrita
  falhava; o nome vira nome de ferramenta e de diretório;
- N5: ``pyyaml`` é dependência declarada (ver requirements.txt).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import yaml

from openjarvis.security.injection_scanner import InjectionScanner
from openjarvis.security.signing import verify_b64
from openjarvis.security.types import ThreatLevel
from openjarvis.skills.types import SkillManifest, SkillStep

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

LOGGER = logging.getLogger(__name__)

# Nome seguro para virar nome de ferramenta/diretório (sem separadores de caminho).
_NOME_SEGURO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class SkillSignatureError(ValueError):
    """Assinatura ausente, inválida ou impossível de verificar."""


class SkillInjectionError(ValueError):
    """O scanner encontrou padrão de injeção grave na skill."""


def _validar_nome(nome: str) -> str:
    if not isinstance(nome, str) or not _NOME_SEGURO.match(nome):
        raise ValueError(f"Nome de skill inválido: {nome!r}")
    return nome


def _ler_toml(path: Path) -> SkillManifest:
    """Lê um skill.toml, SEM verificar assinatura (a verificação é depois)."""
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    skill = data.get("skill", {})

    passos = [
        SkillStep(
            tool_name=p.get("tool_name", ""),
            skill_name=p.get("skill_name", ""),
            arguments_template=p.get("arguments_template", "{}"),
            output_key=p.get("output_key", ""),
        )
        for p in skill.get("steps", [])
    ]
    return SkillManifest(
        name=_validar_nome(skill.get("name", path.stem)),
        version=skill.get("version", "0.1.0"),
        description=skill.get("description", ""),
        author=skill.get("author", ""),
        steps=passos,
        required_capabilities=list(skill.get("required_capabilities", [])),
        signature=skill.get("signature", ""),
        metadata=skill.get("metadata", {}),
        tags=list(skill.get("tags", [])),
        depends=list(skill.get("depends", [])),
        user_invocable=skill.get("user_invocable", True),
        disable_model_invocation=skill.get("disable_model_invocation", False),
    )


def _ler_markdown(path: Path) -> SkillManifest:
    """Lê um SKILL.md (frontmatter YAML + corpo) com validação estrita."""
    from openjarvis.skills.parser import SkillParser

    bruto = path.read_text(encoding="utf-8")
    frontmatter: dict = {}
    corpo = bruto

    if bruto.startswith("---"):
        resto = bruto[3:]
        if resto.startswith("\n"):
            resto = resto[1:]
        fim = resto.find("\n---")
        if fim != -1:
            try:
                carregado = yaml.safe_load(resto[:fim]) or {}
            except yaml.YAMLError as exc:
                raise ValueError(f"Frontmatter YAML inválido em {path}") from exc
            if not isinstance(carregado, dict):
                raise ValueError(f"Frontmatter de {path} deve ser um mapa")
            frontmatter = carregado
            depois = resto[fim + 4 :]
            corpo = depois[1:] if depois.startswith("\n") else depois

    frontmatter.setdefault(
        "name", path.parent.name if path.name == "SKILL.md" else path.stem
    )
    frontmatter.setdefault("description", str(frontmatter["name"]))
    # A assinatura não faz parte do que é assinado: sai do frontmatter.
    assinatura = str(frontmatter.pop("signature", "") or "")

    manifesto = SkillParser().parse_frontmatter(frontmatter, markdown_content=corpo)
    manifesto.signature = assinatura
    return manifesto


def _verificar(
    manifesto: SkillManifest,
    *,
    verify_signature: bool,
    public_key: Optional[bytes],
    scan_for_injection: bool,
) -> SkillManifest:
    """Aplica as verificações pedidas. Qualquer falha LEVANTA exceção."""
    if verify_signature:
        if not public_key:
            raise SkillSignatureError(
                f"Skill '{manifesto.name}': chave pública não informada"
            )
        if not manifesto.signature:
            raise SkillSignatureError(f"Skill '{manifesto.name}': sem assinatura")
        if not verify_b64(manifesto.manifest_bytes(), manifesto.signature, public_key):
            raise SkillSignatureError(f"Skill '{manifesto.name}': assinatura inválida")

    if scan_for_injection:
        scanner = InjectionScanner()
        textos = [manifesto.description, manifesto.markdown_content]
        textos += [p.arguments_template for p in manifesto.steps]
        for texto in textos:
            resultado = scanner.scan(texto or "")
            if not resultado.is_clean and resultado.threat_level in (
                ThreatLevel.HIGH,
                ThreatLevel.CRITICAL,
            ):
                primeiro = resultado.findings[0]
                raise SkillInjectionError(
                    f"Skill '{manifesto.name}': possível injeção de prompt "
                    f"({primeiro.pattern_name})"
                )
    return manifesto


def load_skill(
    path: str | Path,
    *,
    verify_signature: bool = False,
    public_key: Optional[bytes] = None,
    scan_for_injection: bool = False,
) -> SkillManifest:
    """Carrega uma skill de um arquivo TOML (``[skill]`` e ``[[skill.steps]]``)."""
    manifesto = _ler_toml(Path(path))
    return _verificar(
        manifesto,
        verify_signature=verify_signature,
        public_key=public_key,
        scan_for_injection=scan_for_injection,
    )


def load_skill_markdown(
    path: str | Path,
    *,
    verify_signature: bool = False,
    public_key: Optional[bytes] = None,
    scan_for_injection: bool = False,
) -> SkillManifest:
    """Carrega uma skill de um SKILL.md."""
    manifesto = _ler_markdown(Path(path))
    return _verificar(
        manifesto,
        verify_signature=verify_signature,
        public_key=public_key,
        scan_for_injection=scan_for_injection,
    )


def load_skill_directory(
    path: str | Path,
    *,
    verify_signature: bool = False,
    public_key: Optional[bytes] = None,
    scan_for_injection: bool = False,
) -> SkillManifest:
    """Carrega uma skill de um diretório com ``skill.toml`` e/ou ``SKILL.md``.

    Com os dois, o TOML manda nos campos estruturados e o corpo vem do
    SKILL.md. A verificação acontece sobre o manifesto já combinado.
    """
    path = Path(path)
    toml_path = path / "skill.toml"
    md_path = path / "SKILL.md"
    tem_toml, tem_md = toml_path.exists(), md_path.exists()

    if not tem_toml and not tem_md:
        raise FileNotFoundError(
            f"No skill.toml or SKILL.md found in directory '{path}'"
        )

    if tem_toml:
        manifesto = _ler_toml(toml_path)
        if tem_md:
            manifesto.markdown_content = _ler_markdown(md_path).markdown_content
    else:
        manifesto = _ler_markdown(md_path)

    return _verificar(
        manifesto,
        verify_signature=verify_signature,
        public_key=public_key,
        scan_for_injection=scan_for_injection,
    )


def discover_skills(
    directory: str | Path,
    *,
    verify_signature: bool = False,
    public_key: Optional[bytes] = None,
    scan_for_injection: bool = False,
) -> list[SkillManifest]:
    """Varre um diretório e carrega as skills válidas.

    Layouts: ``*.toml`` soltos, ``<dir>/<nome>/{skill.toml,SKILL.md}`` e
    ``<dir>/<origem>/<nome>/...``. Skill que falha (inclusive na verificação)
    é registrada no log e IGNORADA; as demais continuam.
    """
    diretorio = Path(directory).expanduser()
    if not diretorio.exists():
        return []

    opcoes = dict(
        verify_signature=verify_signature,
        public_key=public_key,
        scan_for_injection=scan_for_injection,
    )
    manifestos: list[SkillManifest] = []

    def _tentar(carregar, alvo: Path) -> None:
        try:
            manifestos.append(carregar(alvo, **opcoes))
        except Exception as exc:  # noqa: BLE001 — uma skill ruim não derruba as outras
            LOGGER.warning("Skill ignorada (%s): %s", alvo, exc)

    for arquivo in sorted(diretorio.glob("*.toml")):
        _tentar(load_skill, arquivo)

    for filho in sorted(diretorio.iterdir()):
        if not filho.is_dir() or filho.is_symlink():
            continue
        if (filho / "skill.toml").exists() or (filho / "SKILL.md").exists():
            _tentar(load_skill_directory, filho)
            continue
        for neto in sorted(filho.iterdir()):
            if not neto.is_dir() or neto.is_symlink():
                continue
            if (neto / "skill.toml").exists() or (neto / "SKILL.md").exists():
                _tentar(load_skill_directory, neto)

    return manifestos


__all__ = [
    "SkillInjectionError",
    "SkillSignatureError",
    "discover_skills",
    "load_skill",
    "load_skill_directory",
    "load_skill_markdown",
]
