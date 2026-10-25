"""Limitador de taxa (token bucket) em Python puro.

Patch N16: no upstream o ``RateLimiter`` exigia o módulo Rust e o ``reset``
tinha código morto depois de um ``return``. Aqui o ``TokenBucket`` (que já
existia) é o único backend, com limite de buckets para não crescer sem fim.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

__all__ = ["RateLimitConfig", "RateLimiter", "TokenBucket"]


@dataclass(slots=True)
class RateLimitConfig:
    """Configuração do limitador."""

    requests_per_minute: int = 60
    burst_size: int = 10  # capacidade máxima do balde
    enabled: bool = True
    max_buckets: int = 10_000  # teto de chaves distintas em memória


class TokenBucket:
    """Balde de fichas seguro para threads."""

    def __init__(
        self,
        rate: float,
        capacity: int,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        if rate <= 0:
            raise ValueError("rate deve ser positivo")
        if capacity <= 0:
            raise ValueError("capacity deve ser positivo")
        self._rate = rate  # fichas por segundo
        self._capacity = capacity
        self._tokens = float(capacity)
        self._relogio = relogio
        self._last_refill = relogio()
        self._lock = threading.Lock()

    def consume(self, tokens: int = 1) -> Tuple[bool, float]:
        """Tenta consumir fichas. Devolve ``(permitido, segundos_de_espera)``."""
        with self._lock:
            agora = self._relogio()
            decorrido = max(0.0, agora - self._last_refill)
            self._tokens = min(self._capacity, self._tokens + decorrido * self._rate)
            self._last_refill = agora
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True, 0.0
            return False, (tokens - self._tokens) / self._rate

    @property
    def available(self) -> float:
        """Fichas disponíveis agora (aproximado)."""
        with self._lock:
            decorrido = max(0.0, self._relogio() - self._last_refill)
            return min(self._capacity, self._tokens + decorrido * self._rate)


class RateLimiter:
    """Limitador com um balde por chave (``agente:ferramenta``)."""

    def __init__(
        self,
        config: Optional[RateLimitConfig] = None,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config or RateLimitConfig()
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.Lock()
        self._relogio = relogio

    def check(self, key: str) -> Tuple[bool, float]:
        """Devolve ``(permitido, segundos_de_espera)`` para a chave."""
        if not self._config.enabled:
            return True, 0.0
        return self._get_bucket(key).consume()

    def _get_bucket(self, key: str) -> TokenBucket:
        with self._lock:
            balde = self._buckets.get(key)
            if balde is None:
                if len(self._buckets) >= self._config.max_buckets:
                    # Remove o mais antigo (ordem de inserção do dict).
                    self._buckets.pop(next(iter(self._buckets)))
                balde = TokenBucket(
                    rate=self._config.requests_per_minute / 60.0,
                    capacity=self._config.burst_size,
                    relogio=self._relogio,
                )
                self._buckets[key] = balde
            return balde

    def reset(self, key: Optional[str] = None) -> None:
        """Zera o estado de uma chave (ou de todas)."""
        with self._lock:
            if key:
                self._buckets.pop(key, None)
            else:
                self._buckets.clear()

    @property
    def config(self) -> RateLimitConfig:
        return self._config
