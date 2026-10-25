"""Rastreamento de contaminação (taint) — controle de fluxo de informação.

Patch N18: o upstream tinha PII só dos EUA (SSN, telefone americano), um regex
de segredo genérico que casava com prosa comum ("key: valor...") e o regex de
cartão aceitava qualquer sequência de 16 dígitos. Como o taint é cumulativo na
sessão, um falso positivo bloqueava ``web_search``/``http_request`` até o fim da
execução. Aqui:

- CPF/CNPJ/telefone BR entram como PII (com validação de dígitos);
- cartão exige Luhn; telefone dos EUA exige separadores;
- segredo genérico exige palavra-chave + valor longo/com cara de credencial;
- ``schedule_task`` vira destino proibido para segredos (a tarefa persiste).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, Optional, Set

from openjarvis.security.scanner import _cnpj_valido, _cpf_valido, _luhn_valido


class TaintLabel(str, Enum):
    """Rótulos de dado contaminado."""

    PII = "pii"
    SECRET = "secret"
    USER_PRIVATE = "user_private"
    EXTERNAL = "external"


@dataclass(frozen=True)
class TaintSet:
    """Conjunto imutável de rótulos associado a um dado."""

    labels: FrozenSet[TaintLabel] = field(default_factory=frozenset)

    def union(self, other: "TaintSet") -> "TaintSet":
        """Une dois conjuntos."""
        return TaintSet(labels=self.labels | other.labels)

    def has(self, label: TaintLabel) -> bool:
        """Verifica um rótulo."""
        return label in self.labels

    def __bool__(self) -> bool:
        return bool(self.labels)

    @classmethod
    def from_labels(cls, *labels: TaintLabel) -> "TaintSet":
        """Cria a partir de rótulos."""
        return cls(labels=frozenset(labels))


# Política de destino: quais rótulos são proibidos em cada ferramenta.
SINK_POLICY: Dict[str, Set[TaintLabel]] = {
    "web_search": {TaintLabel.PII, TaintLabel.SECRET},
    # http_request é a principal saída de exfiltração.
    "http_request": {TaintLabel.PII, TaintLabel.SECRET},
    "channel_send": {TaintLabel.SECRET},
    "channel_tools": {TaintLabel.SECRET},
    "code_interpreter": {TaintLabel.SECRET},
    "file_write": {TaintLabel.SECRET},
    # A tarefa agendada fica gravada em disco e roda depois: nada de segredo.
    "schedule_task": {TaintLabel.SECRET},
}

_RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_RE_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_RE_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_RE_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_RE_CARTAO = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_RE_TEL_BR = re.compile(
    r"(?:\+55[\s-]?\(?\d{2}\)?[\s-]?9?\d{4}[\s-]?\d{4})"
    r"|(?:\(\d{2}\)\s?9?\d{4}[\s-]?\d{4})"
)
_RE_TEL_US = re.compile(
    r"(?:\(\d{3}\)[\s.-]?\d{3}[\s.-]\d{4})|(?:\b[2-9]\d{2}[-.\s]\d{3}[-.\s]\d{4}\b)"
)

_PADROES_SEGREDO = [
    re.compile(r"\b(?:sk|pk|rk)[_-](?:live|test|ant)?[_-]?[A-Za-z0-9]{20,}"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"),  # token de bot do Telegram
    re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}"),
    # palavra-chave + valor com cara de credencial (>= 12 caracteres, sem espaço)
    re.compile(
        r"(?i)\b(?:api[_-]?key|secret|token|password|passwd|senha)\b"
        r"\s*[=:]\s*['\"]?[A-Za-z0-9_\-./+=]{12,}"
    ),
]


def check_taint(tool_name: str, taint: TaintSet) -> Optional[str]:
    """Devolve a descrição da violação, ou ``None`` se estiver limpo."""
    proibidos = SINK_POLICY.get(tool_name)
    if proibidos is None:
        return None
    violacoes = taint.labels & proibidos
    if violacoes:
        rotulos = ", ".join(v.value for v in sorted(violacoes, key=lambda x: x.value))
        return f"Data with labels [{rotulos}] cannot be sent to '{tool_name}'."
    return None


def declassify(taint: TaintSet, remove: TaintLabel, reason: str) -> TaintSet:
    """Remove um rótulo. O ``reason`` deve ser registrado por quem chama."""
    return TaintSet(labels=taint.labels - {remove})


def _tem_pii(texto: str) -> bool:
    if _RE_EMAIL.search(texto) or _RE_SSN.search(texto):
        return True
    if _RE_TEL_BR.search(texto) or _RE_TEL_US.search(texto):
        return True
    if any(_cpf_valido(m.group(0)) for m in _RE_CPF.finditer(texto)):
        return True
    if any(_cnpj_valido(m.group(0)) for m in _RE_CNPJ.finditer(texto)):
        return True
    return any(_luhn_valido(m.group(0)) for m in _RE_CARTAO.finditer(texto))


def auto_detect_taint(text: str) -> TaintSet:
    """Detecta rótulos de contaminação em um texto."""
    texto = text or ""
    rotulos: set[TaintLabel] = set()
    if _tem_pii(texto):
        rotulos.add(TaintLabel.PII)
    if any(p.search(texto) for p in _PADROES_SEGREDO):
        rotulos.add(TaintLabel.SECRET)
    return TaintSet(labels=frozenset(rotulos))


def propagate_taint(input_taint: TaintSet, output_text: str) -> TaintSet:
    """União do taint de entrada com o detectado na saída."""
    return input_taint.union(auto_detect_taint(output_text))


__all__ = [
    "SINK_POLICY",
    "TaintLabel",
    "TaintSet",
    "auto_detect_taint",
    "check_taint",
    "declassify",
    "propagate_taint",
]
