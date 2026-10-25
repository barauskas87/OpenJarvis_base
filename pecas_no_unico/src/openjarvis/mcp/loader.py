"""Carrega ferramentas de servidores MCP a partir da configuração.

Patch N20. Diferenças em relação ao upstream:

- servidores ``stdio`` só sobem se o executável estiver em ``allowed_commands``
  (padrão: nenhum). O comando vem de configuração, mas configuração também é
  superfície de ataque (arquivo editável por outra ferramenta);
- servidores HTTP exigem ``https`` (ou ``localhost``) e, se informado,
  ``allowed_hosts``;
- o subprocesso recebe ambiente mínimo; variáveis extras só pelas chaves
  nomeadas em ``env`` da configuração do servidor (copiadas do ambiente real);
- as ferramentas ganham prefixo do servidor (sem colisão com as nativas) e
  exigem confirmação, salvo as listadas em ``trusted_tools``;
- ``reserved_names`` (nomes das ferramentas nativas) nunca são aceitos.

Quem chama precisa manter a lista ``clients`` viva enquanto usar as ferramentas.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
from typing import TYPE_CHECKING, Any, Iterable, Optional

if TYPE_CHECKING:
    from openjarvis.mcp.client import MCPClient
    from openjarvis.tools._stubs import BaseTool

logger = logging.getLogger(__name__)

_HOSTS_LOCAIS = {"localhost", "127.0.0.1", "::1"}


def _url_permitida(url: str, allowed_hosts: Optional[set[str]]) -> Optional[str]:
    """Devolve o motivo da recusa, ou ``None`` se a URL pode ser usada."""
    analisada = urllib.parse.urlparse(url)
    host = (analisada.hostname or "").lower()
    if analisada.scheme not in ("http", "https") or not host:
        return "URL inválida"
    if analisada.scheme == "http" and host not in _HOSTS_LOCAIS:
        return "HTTP em claro só é aceito para localhost"
    if allowed_hosts is not None and host not in allowed_hosts:
        return f"host {host!r} fora da lista permitida"
    return None


def load_mcp_tools_from_config(
    mcp_cfg: Any,
    *,
    allowed_names: Optional[set[str]] = None,
    allowed_commands: Optional[Iterable[str]] = None,
    allowed_hosts: Optional[Iterable[str]] = None,
    reserved_names: Iterable[str] = (),
) -> tuple[list["BaseTool"], list["MCPClient"]]:
    """Carrega ferramentas de todos os servidores de ``mcp_cfg.servers``.

    Devolve ``(tools, clients)``. Falha em um servidor não derruba os demais.
    """
    if not getattr(mcp_cfg, "enabled", False):
        return [], []
    servers_blob = getattr(mcp_cfg, "servers", None)
    if not servers_blob:
        return [], []

    try:
        lista = (
            json.loads(servers_blob) if isinstance(servers_blob, str) else servers_blob
        )
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Failed to parse MCP servers config: %s", exc)
        return [], []
    if not isinstance(lista, list):
        logger.warning("MCP servers config is not a list — skipping MCP discovery")
        return [], []

    from openjarvis.mcp.client import MCPClient
    from openjarvis.mcp.transport import StdioTransport, StreamableHTTPTransport
    from openjarvis.tools.mcp_adapter import MCPToolProvider

    comandos = {os.path.basename(c).lower() for c in (allowed_commands or ())}
    hosts = {h.lower() for h in allowed_hosts} if allowed_hosts is not None else None
    reservados = set(reserved_names)

    tools: list["BaseTool"] = []
    clients: list["MCPClient"] = []

    for item in lista:
        nome = "<sem-nome>"
        client = None
        try:
            cfg = json.loads(item) if isinstance(item, str) else item
            nome = str(cfg.get("name") or "<sem-nome>")
            url = cfg.get("url")
            command = cfg.get("command", "")
            args = list(cfg.get("args", []))

            if url:
                motivo = _url_permitida(url, hosts)
                if motivo:
                    logger.warning("MCP '%s' recusado: %s", nome, motivo)
                    continue
                transporte = StreamableHTTPTransport(url=url, token=cfg.get("token"))
            elif command:
                if os.path.basename(command).lower() not in comandos:
                    logger.warning(
                        "MCP '%s' recusado: comando %r fora de allowed_commands",
                        nome,
                        command,
                    )
                    continue
                env_extra = {
                    chave: os.environ[chave]
                    for chave in cfg.get("env", [])
                    if chave in os.environ
                }
                transporte = StdioTransport(
                    command=[command, *args], env_extra=env_extra
                )
            else:
                logger.warning("MCP server '%s' has neither 'url' nor 'command'", nome)
                continue

            client = MCPClient(transporte)
            client.initialize()
            clients.append(client)

            provedor = MCPToolProvider(
                client,
                servidor=nome,
                exigir_confirmacao=True,
                timeout_segundos=float(cfg.get("timeout_seconds", 120.0)),
            )
            descobertas = provedor.discover(confiaveis=cfg.get("trusted_tools", []))

            incluir = set(cfg.get("include_tools", []))
            excluir = set(cfg.get("exclude_tools", []))
            filtradas = []
            for ferramenta in descobertas:
                nome_local = ferramenta.spec.name
                if nome_local in reservados:
                    logger.warning(
                        "MCP '%s': nome reservado %r ignorado", nome, nome_local
                    )
                    continue
                remoto = getattr(ferramenta, "_nome_remoto", nome_local)
                if incluir and remoto not in incluir:
                    continue
                if remoto in excluir:
                    continue
                if allowed_names and nome_local not in allowed_names:
                    continue
                filtradas.append(ferramenta)
            tools.extend(filtradas)
            logger.info(
                "Discovered %d MCP tools from server '%s'", len(filtradas), nome
            )
        except Exception as exc:  # noqa: BLE001 — isolamento por servidor
            logger.warning("Failed to discover MCP tools from '%s': %s", nome, exc)
            if client is not None and client not in clients:
                try:
                    client.close()
                except Exception:  # noqa: BLE001
                    pass
            continue

    return tools, clients
