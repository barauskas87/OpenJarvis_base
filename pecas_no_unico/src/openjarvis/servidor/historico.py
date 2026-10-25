"""Histórico de conversas em memória, limitado e isolado por dono.

A chave inclui o identificador do token: um token nunca lê a conversa de outro,
mesmo adivinhando o ``conversa_id``.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Callable, List, Tuple

Par = Tuple[str, str]  # (mensagem do usuário, resposta do assistente)


class HistoricoDeConversas:
    """Guarda os últimos pares de cada conversa (LRU + validade)."""

    def __init__(
        self,
        *,
        max_conversas: int = 1000,
        max_pares: int = 20,
        validade_s: float = 3600.0,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_conversas = max_conversas
        self._max_pares = max_pares
        self._validade = validade_s
        self._relogio = relogio
        self._dados: "OrderedDict[Tuple[str, str], Tuple[float, List[Par]]]" = (
            OrderedDict()
        )
        self._trava = threading.Lock()

    def obter(self, dono: str, conversa_id: str) -> List[Par]:
        """Cópia do histórico (vazio se não existir ou tiver expirado)."""
        chave = (dono, conversa_id)
        with self._trava:
            entrada = self._dados.get(chave)
            if entrada is None:
                return []
            ultimo_uso, pares = entrada
            if self._relogio() - ultimo_uso > self._validade:
                del self._dados[chave]
                return []
            return list(pares)

    def registrar(
        self, dono: str, conversa_id: str, usuario: str, resposta: str
    ) -> None:
        """Acrescenta um par e descarta o excedente (pares e conversas)."""
        chave = (dono, conversa_id)
        with self._trava:
            entrada = self._dados.pop(chave, None)
            pares = list(entrada[1]) if entrada else []
            pares.append((usuario, resposta))
            self._dados[chave] = (self._relogio(), pares[-self._max_pares :])
            while len(self._dados) > self._max_conversas:
                self._dados.popitem(last=False)

    def __len__(self) -> int:
        with self._trava:
            return len(self._dados)
