"""Lista de diretórios permitidos para as ferramentas de arquivo.

Patch N19: no upstream, ``allowed_dirs`` vazio significava "sem restrição" e
o padrão vinha de ``load_config()``. Aqui a lista é OBRIGATÓRIA e explícita:
sem ela a ferramenta nem é criada. Não há fallback para configuração ambiente.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional


def validate_allowed_dirs(allowed_dirs: object) -> List[str]:
    """Valida a lista: não vazia, só caminhos de texto não vazios."""
    if not isinstance(allowed_dirs, (list, tuple)) or not allowed_dirs:
        raise ValueError(
            "allowed_dirs é obrigatório: informe ao menos um diretório "
            "(lista vazia não significa 'sem restrição' neste projeto)"
        )
    saida: List[str] = []
    for diretorio in allowed_dirs:
        if not isinstance(diretorio, (str, os.PathLike)):
            raise ValueError("allowed_dirs deve conter apenas caminhos")
        texto = os.fspath(diretorio)
        if not isinstance(texto, str) or not texto.strip():
            raise ValueError("allowed_dirs não pode conter caminho vazio")
        saida.append(texto)
    return saida


def resolve_allowed_dirs(allowed_dirs: Optional[List[str]]) -> List[str]:
    """Devolve ``allowed_dirs`` validado. ``None`` é erro (sem padrão ambiente)."""
    if allowed_dirs is None:
        raise ValueError("allowed_dirs é obrigatório (None não é aceito)")
    return validate_allowed_dirs(allowed_dirs)


def caminho_dentro_de(caminho: Path, raizes: List[Path]) -> bool:
    """True se ``caminho`` (já resolvido) está em uma das ``raizes`` resolvidas."""
    return any(caminho == raiz or caminho.is_relative_to(raiz) for raiz in raizes)
