"""Ferramenta de leitura de arquivo, restrita a diretórios permitidos.

Patch N19 (e C-série): diferenças em relação ao upstream:

- ``allowed_dirs`` obrigatório (ver ``_paths.py``);
- o caminho é RESOLVIDO (symlinks seguidos) e confinado ANTES de qualquer
  outra checagem, então a mensagem de erro não revela se um arquivo fora da
  área existe;
- a política de arquivos sensíveis vale para o original e o resolvido;
- o arquivo é aberto uma vez só e lido com teto de tamanho (sem a janela entre
  ``stat`` e a leitura, e sem delegar a leitura ao Rust);
- ``is_local = True``: só lê dentro da área permitida.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.security.file_policy import is_sensitive_file
from openjarvis.tools._paths import caminho_dentro_de, resolve_allowed_dirs
from openjarvis.tools._stubs import BaseTool, ToolSpec

_MAX_SIZE_BYTES = 1_048_576  # 1 MB


@ToolRegistry.register("file_read")
class FileReadTool(BaseTool):
    """Lê o conteúdo de um arquivo dentro dos diretórios permitidos."""

    tool_id = "file_read"
    is_local = True

    def __init__(self, allowed_dirs: Optional[List[str]] = None) -> None:
        self._allowed_dirs = [
            Path(d).expanduser().resolve() for d in resolve_allowed_dirs(allowed_dirs)
        ]

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="file_read",
            description="Read the contents of a file. Returns the text content.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read.",
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": "Max lines to return (default: all).",
                    },
                },
                "required": ["path"],
            },
            category="filesystem",
        )

    def _negado(self, mensagem: str) -> ToolResult:
        return ToolResult(tool_name="file_read", content=mensagem, success=False)

    def execute(self, **params: Any) -> ToolResult:
        pedido = params.get("path", "")
        if not pedido or not isinstance(pedido, str):
            return self._negado("No path provided.")

        caminho = Path(pedido).expanduser()
        if not caminho.is_absolute():
            # Nome relativo significa "dentro da área", não o cwd do processo.
            caminho = self._allowed_dirs[0] / caminho
        try:
            resolvido = caminho.resolve(strict=False)
        except (OSError, RuntimeError):
            return self._negado(f"Access denied: {pedido}")

        # 1) confinamento — antes de qualquer outra pergunta sobre o arquivo
        if not caminho_dentro_de(resolvido, self._allowed_dirs):
            return self._negado(
                f"Access denied: {pedido} is outside allowed directories."
            )
        # 2) política de sensíveis (original e resolvido)
        if is_sensitive_file(caminho) or is_sensitive_file(resolvido):
            return self._negado(f"Access denied: {pedido} is a sensitive file.")

        # 3) leitura única, com teto, no caminho já resolvido
        # Diretório: no Windows dá PermissionError, no Linux IsADirectoryError.
        if resolvido.is_dir():
            return self._negado(f"Not a file: {pedido}")
        try:
            with open(resolvido, "rb") as arquivo:
                bruto = arquivo.read(_MAX_SIZE_BYTES + 1)
        except FileNotFoundError:
            return self._negado(f"File not found: {pedido}")
        except IsADirectoryError:
            return self._negado(f"Not a file: {pedido}")
        except OSError as exc:
            return self._negado(f"Read error: {exc.__class__.__name__}")
        if len(bruto) > _MAX_SIZE_BYTES:
            return self._negado(f"File too large (max {_MAX_SIZE_BYTES} bytes).")

        texto = bruto.decode("utf-8", errors="replace")
        max_lines = params.get("max_lines")
        if isinstance(max_lines, int) and max_lines > 0:
            texto = "".join(texto.splitlines(keepends=True)[:max_lines])
        return ToolResult(
            tool_name="file_read",
            content=texto,
            success=True,
            metadata={"path": str(resolvido), "size_bytes": len(bruto)},
        )


__all__ = ["FileReadTool"]
