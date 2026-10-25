"""Autenticação por token de portador (Bearer).

O servidor guarda só o hash SHA-256 dos tokens; o token em claro aparece uma
única vez, quando é gerado. Tokens são aleatórios de 256 bits, então um hash
simples (sem sal) é suficiente.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from typing import Iterable, Optional

PREFIXO_TOKEN = "nu_"
TAMANHO_MAX_TOKEN = 256
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def gerar_token() -> str:
    """Gera um token novo (mostrar uma vez ao dono; nunca gravar em claro)."""
    return PREFIXO_TOKEN + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash em hexadecimal do token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AutenticadorToken:
    """Confere tokens contra uma lista fixa de hashes."""

    def __init__(self, hashes: Iterable[str]) -> None:
        validos = []
        for item in hashes:
            texto = str(item).strip().lower()
            if not _HEX64.match(texto):
                raise ValueError("hash de token inválido (esperado SHA-256 em hex)")
            validos.append(texto)
        if not validos:
            # Sem tokens ninguém entraria; melhor falhar na partida do que
            # subir um servidor que parece ligado e não atende ninguém.
            raise ValueError("nenhum token configurado")
        self._hashes = tuple(validos)

    def identificar(self, token: Optional[str]) -> Optional[str]:
        """Devolve um identificador curto do token válido, ou ``None``."""
        if not isinstance(token, str) or not token or len(token) > TAMANHO_MAX_TOKEN:
            return None
        candidato = hash_token(token)
        achado: Optional[str] = None
        # Percorre todos, sem parar no primeiro: tempo não revela a posição.
        for conhecido in self._hashes:
            if hmac.compare_digest(candidato, conhecido):
                achado = conhecido[:12]
        return achado

    def verificar(self, token: Optional[str]) -> bool:
        return self.identificar(token) is not None
