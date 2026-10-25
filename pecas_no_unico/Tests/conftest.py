"""Configuração comum dos testes do Nó Único.

Coloca ``src/`` no caminho de importação e isola o diretório de estado
(``OPENJARVIS_HOME``) em uma pasta temporária por teste.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture(autouse=True)
def estado_isolado(tmp_path, monkeypatch):
    """Cada teste usa seu próprio diretório de estado."""
    home = tmp_path / "estado_no_unico"
    home.mkdir()
    monkeypatch.setenv("OPENJARVIS_HOME", str(home))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    return home


@pytest.fixture
def area(tmp_path):
    """Diretório de trabalho permitido para ferramentas de arquivo."""
    pasta = tmp_path / "area_permitida"
    pasta.mkdir()
    return pasta
