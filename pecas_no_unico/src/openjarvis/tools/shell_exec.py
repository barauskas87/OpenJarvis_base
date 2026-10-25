"""Ferramenta de shell com ambiente mínimo, timeout real e confinamento opcional.

Patch C3 (e N12). Diferenças em relação ao upstream:

- sem o atalho Rust: o upstream montava ambiente limpo e timeout e depois os
  IGNORAVA quando a extensão Rust existia (``sh -c`` herdando todo o ambiente,
  sem timeout, sem limite de saída);
- ``env_passthrough`` não é mais decidido pelo modelo: só passam as variáveis
  listadas no construtor (``env_permitido``), padrão nenhuma;
- ``working_dir`` pode ser confinado a ``allowed_dirs``;
- no timeout mata a ÁRVORE de processos (o upstream matava só o shell);
- o tempo de espera do executor (``spec.timeout_seconds``) é maior que o teto
  interno, para o executor não desistir antes da ferramenta.

A ferramenta continua exigindo confirmação (``requires_confirmation``).
"""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from typing import Any, Iterable, List, Optional

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

_MAX_OUTPUT_BYTES = 102_400  # 100 KB por fluxo
_MAX_TIMEOUT = 300
_DEFAULT_TIMEOUT = 30

_PORTABLE_ENV_KEYS = ("PATH", "HOME", "USER", "LANG", "TERM")
_WINDOWS_ENV_KEYS = (
    "SystemRoot",
    "SystemDrive",
    "COMSPEC",
    "PATHEXT",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "LOCALAPPDATA",
    "APPDATA",
)
_BASE_ENV_KEYS = _PORTABLE_ENV_KEYS + (_WINDOWS_ENV_KEYS if os.name == "nt" else ())


def _matar_arvore(proc: "subprocess.Popen[str]") -> None:
    """Encerra o processo e seus filhos (melhor esforço, multiplataforma)."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


@ToolRegistry.register("shell_exec")
class ShellExecTool(BaseTool):
    """Executa comandos de shell com ambiente sanitizado."""

    tool_id = "shell_exec"

    def __init__(
        self,
        *,
        allowed_dirs: Optional[List[str]] = None,
        env_permitido: Iterable[str] = (),
    ) -> None:
        # None = sem confinamento de diretório (a confirmação ainda vale);
        # lista = o working_dir precisa estar dentro dela.
        self._allowed_dirs = (
            [Path(d).expanduser().resolve() for d in allowed_dirs]
            if allowed_dirs is not None
            else None
        )
        self._env_permitido = frozenset(env_permitido)

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="shell_exec",
            description=(
                "Execute a shell command and return its stdout/stderr."
                " Runs with a minimal environment for security."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 30, max 300).",
                    },
                    "working_dir": {
                        "type": "string",
                        "description": (
                            "Working directory for the command."
                            " Must exist and be a directory."
                        ),
                    },
                },
                "required": ["command"],
            },
            category="system",
            requires_confirmation=True,
            # Maior que o teto interno: o executor não deve desistir antes.
            timeout_seconds=float(_MAX_TIMEOUT + 15),
            required_capabilities=["code:execute"],
        )

    def _montar_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        for chave in _BASE_ENV_KEYS:
            valor = os.environ.get(chave)
            if valor is not None:
                env[chave] = valor
        for chave in self._env_permitido:
            valor = os.environ.get(chave)
            if valor is not None:
                env[chave] = valor
        return env

    @staticmethod
    def _falha(mensagem: str, **meta: Any) -> ToolResult:
        return ToolResult(
            tool_name="shell_exec", content=mensagem, success=False, metadata=meta
        )

    def execute(self, **params: Any) -> ToolResult:
        comando = params.get("command", "")
        if not comando or not isinstance(comando, str):
            return self._falha("No command provided.")

        try:
            timeout = int(params.get("timeout", _DEFAULT_TIMEOUT))
        except (TypeError, ValueError):
            timeout = _DEFAULT_TIMEOUT
        timeout = max(1, min(timeout, _MAX_TIMEOUT))

        working_dir = params.get("working_dir")
        cwd: Optional[str] = None
        if working_dir is not None:
            caminho = Path(str(working_dir)).expanduser()
            if not caminho.exists():
                return self._falha(f"Working directory does not exist: {working_dir}")
            if not caminho.is_dir():
                return self._falha(
                    f"Working directory is not a directory: {working_dir}"
                )
            resolvido = caminho.resolve()
            if self._allowed_dirs is not None and not any(
                resolvido == d or resolvido.is_relative_to(d)
                for d in self._allowed_dirs
            ):
                return self._falha(
                    f"Working directory outside allowed directories: {working_dir}"
                )
            cwd = str(resolvido)

        kwargs: dict[str, Any] = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True

        try:
            proc = subprocess.Popen(
                comando,
                shell=True,  # nosec B602 — ferramenta de shell, atrás de confirmação
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=cwd,
                env=self._montar_env(),
                **kwargs,
            )
        except PermissionError as exc:
            return self._falha(f"Permission denied: {exc}")
        except OSError as exc:
            return self._falha(f"OS error: {exc}")

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _matar_arvore(proc)
            try:
                proc.communicate(timeout=5)
            except Exception:  # noqa: BLE001 — limpeza em melhor esforço
                pass
            return self._falha(
                f"Command timed out after {timeout} seconds.",
                returncode=-1,
                timeout_used=timeout,
                working_dir=cwd,
            )

        if len(stdout) > _MAX_OUTPUT_BYTES:
            stdout = stdout[:_MAX_OUTPUT_BYTES] + "\n... (stdout truncated)"
        if len(stderr) > _MAX_OUTPUT_BYTES:
            stderr = stderr[:_MAX_OUTPUT_BYTES] + "\n... (stderr truncated)"

        secoes: list[str] = []
        if stdout:
            secoes.append(f"=== STDOUT ===\n{stdout}")
        if stderr:
            secoes.append(f"=== STDERR ===\n{stderr}")
        return ToolResult(
            tool_name="shell_exec",
            content="\n".join(secoes) if secoes else "(no output)",
            success=proc.returncode == 0,
            metadata={
                "returncode": proc.returncode,
                "timeout_used": timeout,
                "working_dir": cwd,
            },
        )


__all__ = ["ShellExecTool"]
