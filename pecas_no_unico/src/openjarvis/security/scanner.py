"""Scanners de segredos e PII em Python puro (sem Rust).

Patch N16: no upstream, ``SecretScanner`` e ``PIIScanner`` delegavam tudo ao
Rust e os dicionários ``PATTERNS`` eram dado morto. Aqui os padrões são usados
de verdade. Acrescentados: CPF, CNPJ e telefone brasileiro, validação de Luhn
para cartões e mascaramento do trecho encontrado (o achado nunca carrega o
segredo inteiro, para não vazar em logs/eventos).
"""

from __future__ import annotations

import re
from typing import Dict, List, Pattern, Tuple

from openjarvis.security._stubs import BaseScanner
from openjarvis.security.types import ScanFinding, ScanResult, ThreatLevel

_Padrao = Tuple[str, ThreatLevel, str]


def _luhn_valido(texto: str) -> bool:
    """Valida número de cartão pelo algoritmo de Luhn (ignora separadores)."""
    digitos = [int(c) for c in texto if c.isdigit()]
    if not 13 <= len(digitos) <= 19:
        return False
    soma = 0
    for indice, valor in enumerate(reversed(digitos)):
        if indice % 2 == 1:
            valor *= 2
            if valor > 9:
                valor -= 9
        soma += valor
    return soma % 10 == 0


def _cpf_valido(texto: str) -> bool:
    """Valida dígitos verificadores de CPF (reduz falso positivo)."""
    d = [int(c) for c in texto if c.isdigit()]
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(d[i] * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10 % 11) % 10
        if digito != d[tamanho]:
            return False
    return True


def _cnpj_valido(texto: str) -> bool:
    """Valida dígitos verificadores de CNPJ."""
    d = [int(c) for c in texto if c.isdigit()]
    if len(d) != 14 or len(set(d)) == 1:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for pesos, posicao in ((pesos1, 12), (pesos2, 13)):
        soma = sum(v * p for v, p in zip(d, pesos))
        resto = soma % 11
        digito = 0 if resto < 2 else 11 - resto
        if digito != d[posicao]:
            return False
    return True


# Validadores opcionais por nome de padrão: se existir, o achado só vale quando
# o validador aprovar o trecho.
_VALIDADORES = {
    "credit_card_visa": _luhn_valido,
    "credit_card_mastercard": _luhn_valido,
    "credit_card_amex": _luhn_valido,
    "cpf": _cpf_valido,
    "cnpj": _cnpj_valido,
}


def _mascarar(trecho: str) -> str:
    """Devolve só o início do trecho (nunca o segredo completo)."""
    return trecho[:4] + "…" if len(trecho) > 4 else "…"


class _ScannerPorRegex(BaseScanner):
    """Base: aplica ``PATTERNS`` em ordem e coleta achados."""

    PATTERNS: Dict[str, _Padrao] = {}

    def __init__(self) -> None:
        self._compilados: List[Tuple[str, Pattern[str], ThreatLevel, str]] = [
            (nome, re.compile(regex), nivel, descricao)
            for nome, (regex, nivel, descricao) in self.PATTERNS.items()
        ]

    def scan(self, text: str) -> ScanResult:
        achados: List[ScanFinding] = []
        for nome, regex, nivel, descricao in self._compilados:
            validador = _VALIDADORES.get(nome)
            for m in regex.finditer(text or ""):
                if validador is not None and not validador(m.group(0)):
                    continue
                achados.append(
                    ScanFinding(
                        pattern_name=nome,
                        matched_text=_mascarar(m.group(0)),
                        threat_level=nivel,
                        start=m.start(),
                        end=m.end(),
                        description=descricao,
                    )
                )
        return ScanResult(findings=achados)

    def redact(self, text: str) -> str:
        resultado = text or ""
        for nome, regex, _nivel, _desc in self._compilados:
            validador = _VALIDADORES.get(nome)

            def _troca(m: "re.Match[str]", _n: str = nome, _v=validador) -> str:
                if _v is not None and not _v(m.group(0)):
                    return m.group(0)
                return f"[REDACTED:{_n}]"

            resultado = regex.sub(_troca, resultado)
        return resultado


class SecretScanner(_ScannerPorRegex):
    """Detecta chaves de API, tokens, senhas e outros segredos."""

    scanner_id = "secrets"

    PATTERNS: Dict[str, _Padrao] = {
        # sk-ant- vem antes de sk- para o nome mais específico aparecer primeiro.
        "anthropic_key": (
            r"sk-ant-[A-Za-z0-9_-]{20,}",
            ThreatLevel.CRITICAL,
            "Anthropic API key",
        ),
        "openai_key": (
            r"sk-(?!ant-)[A-Za-z0-9_-]{20,}",
            ThreatLevel.CRITICAL,
            "OpenAI API key",
        ),
        "aws_access_key": (
            r"AKIA[0-9A-Z]{16}",
            ThreatLevel.CRITICAL,
            "AWS access key",
        ),
        "github_token": (
            r"(?:ghp|gho|ghs|ghr|ghu)_[A-Za-z0-9_]{36,}|github_pat_[A-Za-z0-9_]{20,}",
            ThreatLevel.CRITICAL,
            "GitHub token",
        ),
        "telegram_bot_token": (
            r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b",
            ThreatLevel.CRITICAL,
            "Telegram bot token",
        ),
        "google_api_key": (
            r"AIza[0-9A-Za-z_-]{30,}",
            ThreatLevel.HIGH,
            "Google API key",
        ),
        "jwt": (
            r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}",
            ThreatLevel.HIGH,
            "JSON Web Token",
        ),
        "bearer_header": (
            r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}",
            ThreatLevel.HIGH,
            "Authorization bearer",
        ),
        "password_assignment": (
            r"""(?i)(?:password|passwd|pwd|senha)\s*[=:]\s*['"]([^'"]{4,})['"]""",
            ThreatLevel.HIGH,
            "Password assignment",
        ),
        "db_connection_string": (
            r"(?:postgres|postgresql|mysql|mongodb|redis)://[^\s]{10,}",
            ThreatLevel.HIGH,
            "Database connection string",
        ),
        "private_key": (
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
            ThreatLevel.CRITICAL,
            "Private key",
        ),
        "slack_token": (
            r"xox[bpors]-[A-Za-z0-9\-]{10,}",
            ThreatLevel.HIGH,
            "Slack token",
        ),
        "stripe_key": (
            r"(?:sk|pk|rk)_(?:test|live)_[A-Za-z0-9]{20,}",
            ThreatLevel.CRITICAL,
            "Stripe key",
        ),
        "generic_api_key": (
            r"""(?i)(?:api[_-]?key|secret[_-]?key|auth[_-]?token|access[_-]?token)"""
            r"""\s*[=:]\s*['"]([^'"]{8,})['"]""",
            ThreatLevel.HIGH,
            "Generic API key/secret",
        ),
    }


class PIIScanner(_ScannerPorRegex):
    """Detecta dados pessoais (inclui CPF, CNPJ e telefone do Brasil)."""

    scanner_id = "pii"

    PATTERNS: Dict[str, _Padrao] = {
        "email": (
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            ThreatLevel.MEDIUM,
            "Email address",
        ),
        "cpf": (
            r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b",
            ThreatLevel.CRITICAL,
            "CPF",
        ),
        "cnpj": (
            r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b",
            ThreatLevel.HIGH,
            "CNPJ",
        ),
        "br_phone": (
            r"(?:\+55[\s-]?\(?\d{2}\)?[\s-]?9?\d{4}[\s-]?\d{4})"
            r"|(?:\(\d{2}\)\s?9?\d{4}[\s-]?\d{4})",
            ThreatLevel.MEDIUM,
            "Telefone brasileiro",
        ),
        "us_ssn": (
            r"\b\d{3}-\d{2}-\d{4}\b",
            ThreatLevel.CRITICAL,
            "US Social Security Number",
        ),
        "credit_card_visa": (
            r"\b4\d{3}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
            ThreatLevel.CRITICAL,
            "Visa credit card",
        ),
        "credit_card_mastercard": (
            r"\b5[1-5]\d{2}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
            ThreatLevel.CRITICAL,
            "Mastercard credit card",
        ),
        "credit_card_amex": (
            r"\b3[47]\d{2}[\s-]?\d{6}[\s-]?\d{5}\b",
            ThreatLevel.CRITICAL,
            "Amex credit card",
        ),
    }


__all__ = ["PIIScanner", "SecretScanner"]
