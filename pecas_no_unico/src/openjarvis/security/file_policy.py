"""Política de arquivos sensíveis — bloqueia segredos, credenciais e chaves.

Patch N19: o upstream não cobria o próprio diretório de estado do projeto
(``config.toml`` com tokens, ``connectors/*.json`` com OAuth, ``.vault_key``),
comparava nomes com diferença de maiúsculas/minúsculas no Linux (``.ENV``
passava) e dependia do Rust quando disponível. Aqui:

- a comparação ignora maiúsculas/minúsculas em qualquer sistema;
- nomes novos: ``.vault_key``, ``id_ecdsa``, ``*.ppk``, ``*.kdbx``, ``.npmrc``…;
- diretórios inteiros protegidos (``.ssh``, ``.aws``, ``.gnupg``, ``.kube``…);
- tudo dentro do diretório de estado do Nó (``get_config_dir()``) é sensível.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Iterable, Iterator, List, Union

from openjarvis.core.paths import get_config_dir

DEFAULT_SENSITIVE_PATTERNS: frozenset[str] = frozenset(
    {
        ".env",
        ".env.*",
        "*.env",
        ".secret",
        "*.secrets",
        "credentials.*",
        "client_secret*.json",
        "*.pem",
        "*.key",
        "*.p12",
        "*.pfx",
        "*.jks",
        "*.ppk",
        "*.kdbx",
        ".vault_key",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        ".htpasswd",
        ".pgpass",
        ".netrc",
        ".npmrc",
        ".pypirc",
        ".dockercfg",
        ".git-credentials",
        "credentials",
        "shadow",
        "gshadow",
        "pass.txt",
        "password.txt",
        "passwords.txt",
        "senha.txt",
        "senhas.txt",
    }
)

# Diretórios cujo conteúdo inteiro é sensível (qualquer componente do caminho).
DEFAULT_SENSITIVE_DIRS: frozenset[str] = frozenset(
    {".ssh", ".aws", ".gnupg", ".kube", ".docker"}
)


def is_sensitive_file(path: Union[str, Path]) -> bool:
    """Diz se ``path`` casa com a política de arquivos sensíveis.

    Verifica o caminho original, cada alvo da cadeia de symlinks e o caminho
    resolvido, para que um symlink não esconda um nome sensível.
    """
    return any(_caminho_sensivel(c) for c in _paths_for_policy(Path(path)))


def _paths_for_policy(path: Path) -> Iterator[Path]:
    """Gera o caminho, cada salto de symlink e o caminho resolvido."""
    yield path
    candidato = path
    for _ in range(40):
        try:
            alvo = candidato.readlink()
        except (OSError, ValueError):
            break
        candidato = alvo if alvo.is_absolute() else candidato.parent / alvo
        yield candidato

    try:
        yield path.resolve(strict=False)
    except (OSError, RuntimeError):
        return


def _dentro_do_estado(caminho: Path) -> bool:
    """True se o caminho está dentro do diretório de estado do Nó."""
    try:
        raiz = get_config_dir()
    except Exception:  # raiz inválida: não decide por aqui
        return False
    try:
        alvo = caminho.resolve(strict=False)
    except (OSError, RuntimeError):
        alvo = caminho
    try:
        alvo.relative_to(raiz)
    except ValueError:
        return False
    return True


def _caminho_sensivel(caminho: Path) -> bool:
    nome = caminho.name.lower()
    texto = str(caminho).replace("\\", "/").lower()
    for padrao in DEFAULT_SENSITIVE_PATTERNS:
        if fnmatch.fnmatchcase(nome, padrao) or fnmatch.fnmatchcase(texto, padrao):
            return True
    partes = {p.lower() for p in caminho.parts}
    if partes & DEFAULT_SENSITIVE_DIRS:
        return True
    return _dentro_do_estado(caminho)


# Compatibilidade com o nome usado no upstream.
_is_sensitive_file_py = lambda path_str: _caminho_sensivel(Path(path_str))  # noqa: E731


def filter_sensitive_paths(paths: Iterable[Union[str, Path]]) -> List[Path]:
    """Devolve só os caminhos que não são sensíveis."""
    return [Path(p) for p in paths if not is_sensitive_file(p)]


__all__ = [
    "DEFAULT_SENSITIVE_DIRS",
    "DEFAULT_SENSITIVE_PATTERNS",
    "filter_sensitive_paths",
    "is_sensitive_file",
]
