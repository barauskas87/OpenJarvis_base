"""Modelos da API do Nó (contrato com o app Android).

Qualquer mudança aqui é mudança de contrato: atualizar também
``contrato/*.json`` e o cliente Kotlin.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

TAMANHO_MAX_MENSAGEM = 8000
PADRAO_CONVERSA_ID = r"^[A-Za-z0-9_-]{1,64}$"


class PedidoConversa(BaseModel):
    """Corpo de ``POST /v1/conversar``."""

    # Campo desconhecido é erro: o cliente e o servidor precisam concordar.
    model_config = ConfigDict(extra="forbid")

    mensagem: str = Field(min_length=1, max_length=TAMANHO_MAX_MENSAGEM)
    conversa_id: Optional[str] = Field(default=None, pattern=PADRAO_CONVERSA_ID)

    @field_validator("mensagem")
    @classmethod
    def mensagem_nao_pode_ser_so_espaco(cls, valor: str) -> str:
        if not valor.strip():
            raise ValueError("mensagem vazia")
        return valor


class RespostaConversa(BaseModel):
    """Resposta de ``POST /v1/conversar``."""

    resposta: str
    conversa_id: str
    turnos: int


class RespostaSaude(BaseModel):
    """Resposta de ``GET /v1/saude`` (sem autenticação, sem detalhes internos)."""

    status: str
    versao_api: str


class RespostaErro(BaseModel):
    """Formato único de erro."""

    erro: str
    mensagem: str
