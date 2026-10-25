"""Sobe a API REAL do Nó com TLS autoassinado, para testes de ponta a ponta.

Usado pelos testes do cliente Kotlin (e útil para testar o app à mão). O
conversador é um eco; tudo o mais (autenticação, limites, validação, TLS) é o
código de produção.

Imprime UMA linha JSON no stdout quando estiver pronto:
    {"porta": 12345, "token": "nu_...", "certificado_pem": "-----BEGIN..."}
e encerra quando o stdin for fechado.
"""

from __future__ import annotations

import datetime
import ipaddress
import json
import socket
import sys
import tempfile
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import uvicorn  # noqa: E402
from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

from openjarvis.servidor.aplicacao import criar_aplicacao  # noqa: E402
from openjarvis.servidor.autenticacao import (  # noqa: E402
    AutenticadorToken,
    gerar_token,
    hash_token,
)
from openjarvis.servidor.conversador import ResultadoConversa  # noqa: E402


class ConversadorEco:
    def conversar(self, mensagem, historico):
        return ResultadoConversa(resposta=f"eco:{mensagem}", turnos=len(historico) + 1)


def gerar_certificado() -> tuple[bytes, bytes]:
    chave = ec.generate_private_key(ec.SECP256R1())
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    agora = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - datetime.timedelta(minutes=5))
        .not_valid_after(agora + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(chave, hashes.SHA256())
    )
    pem_cert = cert.public_bytes(serialization.Encoding.PEM)
    pem_chave = chave.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return pem_cert, pem_chave


def main() -> int:
    token = gerar_token()
    app = criar_aplicacao(
        ConversadorEco(),
        AutenticadorToken([hash_token(token)]),
        requisicoes_por_minuto=6000,
        rajada=1000,
        max_simultaneas=16,
    )
    pem_cert, pem_chave = gerar_certificado()
    pasta = tempfile.mkdtemp(prefix="no_teste_")
    arq_cert, arq_chave = Path(pasta, "c.pem"), Path(pasta, "k.pem")
    arq_cert.write_bytes(pem_cert)
    arq_chave.write_bytes(pem_chave)

    soquete = socket.socket()
    soquete.bind(("127.0.0.1", 0))
    porta = soquete.getsockname()[1]
    servidor = uvicorn.Server(
        uvicorn.Config(
            app,
            fd=soquete.fileno(),
            ssl_certfile=str(arq_cert),
            ssl_keyfile=str(arq_chave),
            log_level="critical",
        )
    )
    fio = threading.Thread(target=servidor.run, daemon=True)
    fio.start()
    while not servidor.started:
        fio.join(0.05)
    print(
        json.dumps(
            {"porta": porta, "token": token, "certificado_pem": pem_cert.decode()}
        ),
        flush=True,
    )
    sys.stdin.read()  # bloqueia até o processo-pai fechar o stdin
    servidor.should_exit = True
    fio.join(5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
