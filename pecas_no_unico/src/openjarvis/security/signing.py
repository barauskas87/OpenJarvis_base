"""Ed25519 signing — supply chain integrity for agent and skill manifests."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class KeyPair:
    """Ed25519 key pair."""

    private_key: bytes
    public_key: bytes


def generate_keypair() -> KeyPair:
    """Generate a new Ed25519 key pair.

    Requires the ``cryptography`` package
    (``uv sync --extra security-signing``).
    """
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = Ed25519PrivateKey.generate()
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return KeyPair(private_key=private_bytes, public_key=public_bytes)
    except ImportError as exc:
        raise ImportError(
            "Ed25519 signing requires the 'cryptography' package. "
            "Install with: uv sync --extra security-signing"
        ) from exc


def sign(data: bytes, private_key: bytes) -> bytes:
    """Sign *data* with an Ed25519 *private_key*.

    Returns the raw 64-byte signature.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        key = Ed25519PrivateKey.from_private_bytes(private_key)
        return key.sign(data)
    except ImportError as exc:
        raise ImportError(
            "Ed25519 signing requires the 'cryptography' package."
        ) from exc


def verify(data: bytes, signature: bytes, public_key: bytes) -> bool:
    """Verify an Ed25519 *signature* on *data* with *public_key*.

    Returns True if valid, False otherwise (inclusive entrada malformada).
    """
    if not signature or not public_key:
        return False
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        try:
            key = Ed25519PublicKey.from_public_bytes(public_key)
            key.verify(signature, data)
            return True
        except (InvalidSignature, ValueError):
            return False
    except ImportError as exc:
        raise ImportError(
            "Ed25519 signing requires the 'cryptography' package."
        ) from exc


def sign_b64(data: bytes, private_key: bytes) -> str:
    """Sign and return base64-encoded signature string."""
    raw = sign(data, private_key)
    return base64.b64encode(raw).decode("ascii")


def verify_b64(data: bytes, signature_b64: str, public_key: bytes) -> bool:
    """Verify a base64-encoded signature."""
    try:
        raw = base64.b64decode(signature_b64)
    except Exception as exc:
        logger.warning("Signature verification failed: %s", exc)
        return False
    return verify(data, raw, public_key)


def load_public_key(path: str) -> bytes:
    """Load a raw 32-byte Ed25519 public key from a file."""
    from pathlib import Path

    raw = Path(path).read_bytes()
    # If base64-encoded (common), decode
    if len(raw) > 32:
        try:
            raw = base64.b64decode(raw.strip())
        except Exception as exc:
            logger.warning("Failed to base64-decode public key from %s: %s", path, exc)
    return raw


def _gravar_privado(caminho: str, conteudo: str) -> None:
    """Grava arquivo com permissão 0600 desde a criação (sem janela aberta)."""
    import os

    descritor = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descritor, "w", encoding="utf-8") as arquivo:
            arquivo.write(conteudo)
    except Exception:
        try:
            os.close(descritor)
        except OSError:
            pass
        raise
    try:
        os.chmod(caminho, 0o600)  # corrige arquivo pré-existente com permissão aberta
    except OSError:
        pass


def save_keypair(keypair: KeyPair, private_path: str, public_path: str) -> None:
    """Salva o par de chaves (base64). A chave privada fica com permissão 0600.

    Patch N25: o upstream usava ``write_text`` (permissão padrão do sistema,
    por exemplo 0644) para a chave privada.
    """
    from pathlib import Path

    _gravar_privado(private_path, base64.b64encode(keypair.private_key).decode())
    Path(public_path).write_text(base64.b64encode(keypair.public_key).decode())


__all__ = [
    "KeyPair",
    "generate_keypair",
    "load_public_key",
    "save_keypair",
    "sign",
    "sign_b64",
    "verify",
    "verify_b64",
]
