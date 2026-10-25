"""Linha de comando do servidor: gerar token e servir a API.

Uso:
    python -m openjarvis.servidor gerar-token
    python -m openjarvis.servidor servir --modelo NOME --certificado c.pem --chave k.pem

Regra de segurança: fora de ``127.0.0.1`` o servidor exige TLS (certificado e
chave) ou a declaração explícita de que há um proxy com TLS na frente.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from openjarvis.servidor.autenticacao import AutenticadorToken, gerar_token, hash_token

VARIAVEL_HASHES = "NO_UNICO_TOKEN_HASHES"
_LOCAIS = {"127.0.0.1", "::1", "localhost"}


def ler_hashes(arquivo: Optional[str], ambiente: Optional[str]) -> List[str]:
    """Hashes vêm de um arquivo (um por linha) e/ou da variável de ambiente."""
    hashes: List[str] = []
    if arquivo:
        with open(arquivo, encoding="utf-8") as f:
            hashes += [linha.strip() for linha in f if linha.strip()]
    if ambiente:
        hashes += [p.strip() for p in ambiente.split(",") if p.strip()]
    return hashes


def validar_exposicao(
    host: str, certificado: Optional[str], chave: Optional[str], atras_de_proxy: bool
) -> Optional[str]:
    """Devolve o motivo da recusa, ou ``None`` se a configuração é segura."""
    if bool(certificado) != bool(chave):
        return "informe certificado e chave juntos"
    if host in _LOCAIS or certificado or atras_de_proxy:
        return None
    return (
        "fora de localhost é obrigatório TLS (--certificado/--chave) "
        "ou --atras-de-proxy-tls"
    )


def montar_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="openjarvis.servidor")
    sub = p.add_subparsers(dest="comando", required=True)
    sub.add_parser("gerar-token", help="gera um token e mostra o hash para configurar")
    s = sub.add_parser("servir", help="sobe a API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--porta", type=int, default=8443)
    s.add_argument("--certificado")
    s.add_argument("--chave")
    s.add_argument("--atras-de-proxy-tls", action="store_true")
    s.add_argument("--arquivo-tokens")
    s.add_argument("--motor-host", default="http://127.0.0.1:8000")
    s.add_argument("--modelo", required=True)
    return p


def principal(argv: Optional[List[str]] = None) -> int:
    args = montar_parser().parse_args(argv)
    if args.comando == "gerar-token":
        token = gerar_token()
        print("TOKEN (mostrado uma vez; entregue ao app):", token)
        print(f"HASH  (guarde no servidor, {VARIAVEL_HASHES}):", hash_token(token))
        return 0

    motivo = validar_exposicao(
        args.host, args.certificado, args.chave, args.atras_de_proxy_tls
    )
    if motivo:
        print("Recusado:", motivo, file=sys.stderr)
        return 2
    try:
        autenticador = AutenticadorToken(
            ler_hashes(args.arquivo_tokens, os.environ.get(VARIAVEL_HASHES))
        )
    except ValueError as exc:
        print("Recusado:", exc, file=sys.stderr)
        return 2

    import uvicorn

    from openjarvis.agents.native_react import NativeReActAgent
    from openjarvis.servidor.aplicacao import criar_aplicacao
    from openjarvis.servidor.conversador import ConversadorAgente
    from openjarvis.servidor.motor import MotorOpenAICompativel

    motor = MotorOpenAICompativel(args.motor_host)
    conversador = ConversadorAgente(
        # Sem ferramentas por padrão: o app só conversa. Ferramentas entram
        # depois, com política de capacidades explícita.
        lambda: NativeReActAgent(motor, args.modelo, tools=[])
    )
    app = criar_aplicacao(conversador, autenticador)
    uvicorn.run(
        app,
        host=args.host,
        port=args.porta,
        ssl_certfile=args.certificado,
        ssl_keyfile=args.chave,
        log_level="warning",
        server_header=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
