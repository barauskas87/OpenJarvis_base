"""Motor OpenAI-compatível (N24), Telegram (N22), guardrails (N17) e assinatura (N25)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import stat
import time
from types import SimpleNamespace

import httpx
import pytest

from apoio import MotorDeStream
from openjarvis.channels._stubs import ChannelStatus
from openjarvis.channels.telegram import TelegramChannel
from openjarvis.core.events import EventBus, EventType
from openjarvis.core.types import Message, Role
from openjarvis.engine._base import EngineConnectionError
from openjarvis.engine._openai_compat import _OpenAICompatibleEngine
from openjarvis.engine._stubs import StreamChunk
from openjarvis.security.boundary import BoundaryGuard, SecurityBlockError
from openjarvis.security.guardrails import GuardrailsEngine
from openjarvis.security.signing import (
    generate_keypair,
    load_public_key,
    save_keypair,
    sign,
    sign_b64,
    verify,
    verify_b64,
)
from openjarvis.security.types import RedactionMode

CHAVE = "sk-" + "a1B2c3D4e5F6g7H8i9J0k1L2"


# --------------------------------------------------------------------------
# Motor
# --------------------------------------------------------------------------
class MotorTeste(_OpenAICompatibleEngine):
    engine_id = "gateway-teste"
    _default_host = "http://gateway.local"

    def _dormir_nada(self, s):  # pragma: no cover
        pass


def motor_com(gerente, **kw):
    m = MotorTeste(**kw)
    m._client = httpx.Client(transport=httpx.MockTransport(gerente), base_url=m._host)  # noqa: SLF001
    m._dormir = lambda s: None  # noqa: SLF001 — sem esperar nos testes
    return m


OK = {
    "choices": [{"message": {"content": "olá"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 3, "completion_tokens": 2},
    "model": "m",
}
MSGS = [Message(role=Role.USER, content="oi")]


@pytest.mark.funcao
class TestMotor:
    def test_resposta_normal(self):
        r = motor_com(lambda req: httpx.Response(200, json=OK)).generate(
            MSGS, model="m"
        )
        assert r["content"] == "olá" and r["usage"]["completion_tokens"] == 2

    def test_host_e_chave_vem_do_ambiente(self, monkeypatch):
        monkeypatch.setenv("GATEWAY_TESTE_HOST", "http://meu-gateway:9000/")
        monkeypatch.setenv("GATEWAY_TESTE_API_KEY", "chave-do-gateway")
        m = MotorTeste()
        assert m._host == "http://meu-gateway:9000"  # noqa: SLF001
        assert m._headers == {"Authorization": "Bearer chave-do-gateway"}  # noqa: SLF001
        m.close()

    def test_nome_do_modelo_passa_direto(self):
        vistos = {}

        def h(req):
            vistos.update(json.loads(req.content))
            return httpx.Response(200, json=OK)

        motor_com(h).generate(MSGS, model="qwen2.5:7b-instruct")
        assert vistos["model"] == "qwen2.5:7b-instruct"

    def test_tool_calls_extraidas(self):
        corpo = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "c1",
                                "function": {"name": "eco", "arguments": '{"a":1}'},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }
        r = motor_com(lambda req: httpx.Response(200, json=corpo)).generate(
            MSGS, model="m"
        )
        assert r["tool_calls"] == [{"id": "c1", "name": "eco", "arguments": '{"a":1}'}]


@pytest.mark.estabilidade
class TestMotorEstabilidade:
    def test_n24_repete_em_falha_transitoria(self):
        respostas = [
            httpx.Response(503),
            httpx.Response(429, headers={"retry-after": "1"}),
            httpx.Response(200, json=OK),
        ]
        chamadas = []

        def h(req):
            chamadas.append(1)
            return respostas[len(chamadas) - 1]

        assert motor_com(h).generate(MSGS, model="m")["content"] == "olá"
        assert len(chamadas) == 3

    def test_desiste_depois_das_tentativas(self):
        chamadas = []

        def h(req):
            chamadas.append(1)
            return httpx.Response(503, text="indisponível")

        with pytest.raises(EngineConnectionError, match="503"):
            motor_com(h).generate(MSGS, model="m")
        assert len(chamadas) == 4  # 1 + 3 tentativas

    def test_400_que_fala_de_tools_repete_sem_tools(self):
        corpos = []

        def h(req):
            corpo = json.loads(req.content)
            corpos.append(corpo)
            if "tools" in corpo:
                return httpx.Response(400, text="this model does not support tools")
            return httpx.Response(200, json=OK)

        r = motor_com(h).generate(MSGS, model="m", tools=[{"type": "function"}])
        assert r["content"] == "olá" and "tools" not in corpos[-1] and len(corpos) == 2

    def test_400_de_outro_assunto_nao_e_escondido(self):
        chamadas = []

        def h(req):
            chamadas.append(1)
            return httpx.Response(400, text="max_tokens must be positive")

        with pytest.raises(EngineConnectionError, match="400"):
            motor_com(h).generate(MSGS, model="m", tools=[{"type": "function"}])
        assert len(chamadas) == 1

    @pytest.mark.parametrize(
        "resposta",
        [
            httpx.Response(200, text="<html>erro</html>"),
            httpx.Response(200, json=[1, 2]),
            httpx.Response(200, json={"choices": [{"sem_message": 1}]}),
            httpx.Response(200, json={"choices": ["texto"]}),
        ],
    )
    def test_corpos_malformados_viram_erro_claro(self, resposta):
        with pytest.raises(EngineConnectionError):
            motor_com(lambda req: resposta).generate(MSGS, model="m")

    def test_sem_choices_devolve_vazio(self):
        r = motor_com(lambda req: httpx.Response(200, json={"choices": []})).generate(
            MSGS, model="m"
        )
        assert r["content"] == "" and r["finish_reason"] == "error"

    def test_servidor_fora_do_ar(self):
        def h(req):
            raise httpx.ConnectError("recusou", request=req)

        with pytest.raises(EngineConnectionError, match="not reachable"):
            motor_com(h).generate(MSGS, model="m")

    def test_404_explica_que_nao_e_servidor_openai(self):
        with pytest.raises(EngineConnectionError, match="OpenAI-compatible"):
            motor_com(lambda req: httpx.Response(404, text="nada")).generate(
                MSGS, model="m"
            )

    def test_saude_e_modelos(self):
        m = motor_com(
            lambda req: httpx.Response(200, json={"data": [{"id": "a"}, {"id": "b"}]})
        )
        assert m.health() and m.list_models() == ["a", "b"]
        ruim = motor_com(lambda req: httpx.Response(500))
        assert not ruim.health() and ruim.list_models() == []


# --------------------------------------------------------------------------
# Telegram
# --------------------------------------------------------------------------
class UpdateFalso:
    def __init__(self, user, chat, texto="oi", mid=1):
        self.message = SimpleNamespace(
            from_user=SimpleNamespace(id=user) if user is not None else None,
            chat=SimpleNamespace(id=chat),
            text=texto,
            message_id=mid,
        )


def canal(**kw):
    return TelegramChannel("123456:TOKEN-SECRETO-DE-TESTE", **kw)


@pytest.mark.funcao
class TestTelegramAutorizacao:
    @pytest.mark.parametrize(
        "users,chats,user,chat,esperado",
        [
            ("111", "", "111", "999", True),
            ("111,222", "", "222", "999", True),
            ("111", "", "333", "999", False),
            ("", "", "111", "999", False),  # lista vazia: ninguém
            ("111", "-100", "111", "-100", True),
            ("111", "-100", "111", "-200", False),  # usuário ok, chat fora
            ("111", "-100", "333", "-100", False),  # chat ok, usuário fora (grupo)
            ([111, 222], [], "111", "5", True),
            ("111", "", "", "5", False),
        ],
    )
    def test_matriz(self, users, chats, user, chat, esperado):
        c = canal(allowed_user_ids=users, allowed_chat_ids=chats)
        assert c.autorizado(user, chat) is esperado

    def test_n22_sem_lista_de_usuarios_nao_conecta(self, caplog):
        c = canal()
        with caplog.at_level(logging.ERROR):
            c.connect()
        assert c.status() == ChannelStatus.ERROR and c._pool is None  # noqa: SLF001
        assert "allowed_user_ids" in caplog.text

    def test_com_lista_conecta_e_desconecta(self):
        c = canal(allowed_user_ids="111")
        c.connect()
        try:
            assert c.status() == ChannelStatus.CONNECTED and c._pool is not None  # noqa: SLF001
        finally:
            c.disconnect()
        assert c.status() == ChannelStatus.DISCONNECTED and c._pool is None  # noqa: SLF001

    def test_sem_token_nao_conecta(self):
        c = TelegramChannel("", allowed_user_ids="1")
        c.connect()
        assert c.status() == ChannelStatus.ERROR


@pytest.mark.integracao
class TestTelegramDespacho:
    def conectado(self, **kw):
        c = canal(allowed_user_ids="111", **kw)
        c.connect()
        return c

    def test_usuario_nao_autorizado_e_ignorado_sem_chamar_handler(self):
        c = self.conectado()
        vistos = []
        c.on_message(lambda cm: vistos.append(cm))
        try:
            asyncio.run(c._tratar_update(UpdateFalso(333, 5)))  # noqa: SLF001
            asyncio.run(c._tratar_update(UpdateFalso(None, 5)))  # noqa: SLF001
            asyncio.run(c._tratar_update(SimpleNamespace(message=None)))  # noqa: SLF001
        finally:
            c.disconnect()
        assert vistos == []

    def test_usuario_autorizado_chega_ao_handler(self):
        c = self.conectado()
        vistos = []
        c.on_message(lambda cm: vistos.append(cm))
        try:
            asyncio.run(c._tratar_update(UpdateFalso(111, 5, "olá", 77)))  # noqa: SLF001
        finally:
            c.disconnect()
        (cm,) = vistos
        assert (cm.sender, cm.conversation_id, cm.message_id, cm.content) == (
            "111",
            "5",
            "77",
            "olá",
        )

    def test_resposta_do_handler_e_enviada(self, monkeypatch):
        c = self.conectado()
        enviados = []
        monkeypatch.setattr(
            c,
            "send",
            lambda canal_, texto, **kw: enviados.append((canal_, texto, kw)) or True,
        )
        c.on_message(lambda cm: "resposta do agente")
        try:
            asyncio.run(c._tratar_update(UpdateFalso(111, 5, "oi", 9)))  # noqa: SLF001
        finally:
            c.disconnect()
        assert enviados == [("5", "resposta do agente", {"conversation_id": "9"})]

    def test_handler_que_levanta_nao_derruba_os_demais(self):
        c = self.conectado()
        vistos = []

        def quebrado(cm):
            raise RuntimeError("x")

        c.on_message(quebrado)
        c.on_message(lambda cm: vistos.append(1))
        try:
            asyncio.run(c._tratar_update(UpdateFalso(111, 5)))  # noqa: SLF001
        finally:
            c.disconnect()
        assert vistos == [1]

    def test_n22_handler_lento_nao_trava_as_outras_mensagens(self):
        c = self.conectado(max_workers=4)
        c.on_message(lambda cm: time.sleep(0.4))

        async def tudo():
            await asyncio.gather(
                *[c._tratar_update(UpdateFalso(111, i)) for i in range(4)]
            )  # noqa: SLF001

        t0 = time.time()
        try:
            asyncio.run(tudo())
        finally:
            c.disconnect()
        assert time.time() - t0 < 1.2  # em série seria ≥ 1,6 s

    def test_evento_publicado_no_barramento(self):
        bus = EventBus()
        eventos = []
        bus.subscribe(EventType.CHANNEL_MESSAGE_RECEIVED, eventos.append)
        c = self.conectado(bus=bus)
        try:
            asyncio.run(c._tratar_update(UpdateFalso(111, 5)))  # noqa: SLF001
        finally:
            c.disconnect()
        assert len(eventos) == 1


@pytest.mark.estabilidade
class TestTelegramEnvio:
    def test_token_nunca_aparece_no_log(self, monkeypatch, caplog):
        c = canal(allowed_user_ids="1")

        def post(url, **kw):
            raise httpx.ConnectError(f"falha em {url}")

        monkeypatch.setattr(httpx, "post", post)
        with caplog.at_level(logging.DEBUG):
            assert c.send("5", "oi") is False
        assert "TOKEN-SECRETO-DE-TESTE" not in caplog.text

    def test_status_http_ruim_nao_vaza_token(self, monkeypatch, caplog):
        c = canal(allowed_user_ids="1")
        monkeypatch.setattr(
            httpx,
            "post",
            lambda url, **kw: httpx.Response(
                401, text="bot123456:TOKEN-SECRETO-DE-TESTE invalido"
            ),
        )
        with caplog.at_level(logging.DEBUG):
            assert c.send("5", "oi") is False
        assert "TOKEN-SECRETO-DE-TESTE" not in caplog.text

    def test_mensagem_longa_e_dividida_e_vazia_nao_envia(self, monkeypatch):
        c = canal(allowed_user_ids="1")
        corpos = []

        def post(url, json=None, **kw):
            corpos.append(json)
            return httpx.Response(200, json={"ok": True})

        monkeypatch.setattr(httpx, "post", post)
        assert c.send("5", "palavra " * 2000)
        assert len(corpos) >= 4 and all(len(b["text"]) <= 4096 for b in corpos)
        assert c.send("5", "") is False

    def test_markdown_rejeitado_repete_como_texto_puro(self, monkeypatch):
        c = canal(allowed_user_ids="1")
        chamadas = []

        def post(url, json=None, **kw):
            chamadas.append(json)
            if "parse_mode" in json:
                return httpx.Response(400, text="can't parse entities")
            return httpx.Response(200, json={"ok": True})

        monkeypatch.setattr(httpx, "post", post)
        assert c.send("5", "a_b*c")
        assert "parse_mode" not in chamadas[-1] and len(chamadas) == 2


# --------------------------------------------------------------------------
# Guardrails e fronteira (N16, N17)
# --------------------------------------------------------------------------
async def coletar(gerador):
    return [x async for x in gerador]


@pytest.mark.funcao
class TestBoundary:
    def test_modos(self):
        texto = f"chave {CHAVE}"
        assert CHAVE not in BoundaryGuard(mode="redact").scan_outbound(texto, "x")
        assert BoundaryGuard(mode="warn").scan_outbound(texto, "x") == texto
        with pytest.raises(SecurityBlockError):
            BoundaryGuard(mode="block").scan_outbound(texto, "x")
        assert (
            BoundaryGuard(mode="block", enabled=False).scan_outbound(texto, "x")
            == texto
        )

    def test_alerta_nao_carrega_o_segredo(self):
        bus = EventBus()
        alertas = []
        bus.subscribe(EventType.SECURITY_ALERT, alertas.append)
        BoundaryGuard(mode="redact", bus=bus).scan_outbound(f"chave {CHAVE}", "tool:x")
        assert alertas and CHAVE not in json.dumps(alertas[0].data)
        assert "content_preview" not in alertas[0].data

    def test_scanners_padrao_sao_reais(self):
        g = BoundaryGuard()
        assert len(g._scanners) == 2  # noqa: SLF001

    def test_uma_unica_classe_de_erro_de_bloqueio(self):
        from openjarvis.security import guardrails

        assert guardrails.SecurityBlockError is SecurityBlockError


@pytest.mark.funcao
class TestGuardrailsStreaming:
    def test_n17_redact_nao_deixa_segredo_dividido_em_pedacos_escapar(self):
        pedacos = ["minha chave é sk-", "a1B2c3D4e5F6", "g7H8i9J0k1L2", " fim"]
        g = GuardrailsEngine(MotorDeStream(pedacos), mode=RedactionMode.REDACT)
        saida = "".join(
            asyncio.run(
                coletar(g.stream([Message(role=Role.USER, content="oi")], model="m"))
            )
        )
        assert CHAVE not in saida and "[REDACTED:openai_key]" in saida

    def test_n17_block_levanta_e_nada_vaza(self):
        g = GuardrailsEngine(
            MotorDeStream(["sk-", CHAVE[3:]]), mode=RedactionMode.BLOCK
        )
        entregue = []

        async def rodar():
            async for token in g.stream(
                [Message(role=Role.USER, content="oi")], model="m"
            ):
                entregue.append(token)

        with pytest.raises(SecurityBlockError):
            asyncio.run(rodar())
        assert entregue == []

    def test_warn_continua_em_streaming_de_verdade(self):
        g = GuardrailsEngine(MotorDeStream(["a", "b", "c"]), mode=RedactionMode.WARN)
        primeiros = []

        async def rodar():
            async for token in g.stream(
                [Message(role=Role.USER, content="oi")], model="m"
            ):
                primeiros.append(token)

        asyncio.run(rodar())
        assert primeiros == ["a", "b", "c"]

    def test_stream_full_preserva_tool_calls_e_finish(self):
        extras = [
            StreamChunk(
                tool_calls=[{"id": "1"}], finish_reason="tool_calls", usage={"t": 1}
            )
        ]
        g = GuardrailsEngine(
            MotorDeStream([f"x {CHAVE}"], extras), mode=RedactionMode.REDACT
        )
        chunks = asyncio.run(
            coletar(g.stream_full([Message(role=Role.USER, content="oi")], model="m"))
        )
        assert CHAVE not in "".join(c.content or "" for c in chunks)
        assert (
            chunks[-1].tool_calls == [{"id": "1"}]
            and chunks[-1].finish_reason == "tool_calls"
        )

    def test_entrada_com_segredo_e_redigida_antes_de_ir_ao_motor(self):
        vistos = []

        class Espiao(MotorDeStream):
            def generate(self, messages, **kw):
                vistos.extend(m.content for m in messages)
                return {"content": "ok"}

        g = GuardrailsEngine(Espiao([]), mode=RedactionMode.REDACT)
        g.generate([Message(role=Role.USER, content=f"use {CHAVE}")], model="m")
        assert vistos and CHAVE not in vistos[0]

    def test_saida_de_generate_e_redigida(self):
        class Vaza(MotorDeStream):
            def generate(self, messages, **kw):
                return {"content": f"a chave é {CHAVE}"}

        r = GuardrailsEngine(Vaza([]), mode=RedactionMode.REDACT).generate(
            [Message(role=Role.USER, content="oi")], model="m"
        )
        assert CHAVE not in r["content"]

    def test_padrao_do_guarda_e_redigir(self):
        assert GuardrailsEngine(MotorDeStream([]))._mode == RedactionMode.REDACT  # noqa: SLF001


# --------------------------------------------------------------------------
# Assinatura (N25)
# --------------------------------------------------------------------------
@pytest.mark.funcao
class TestAssinatura:
    def test_assina_e_verifica(self):
        par = generate_keypair()
        s = sign(b"dado", par.private_key)
        assert verify(b"dado", s, par.public_key)
        assert not verify(b"outro", s, par.public_key)
        assert verify_b64(b"dado", sign_b64(b"dado", par.private_key), par.public_key)

    @pytest.mark.estabilidade
    @pytest.mark.parametrize(
        "assinatura,chave",
        [(b"", b"x" * 32), (b"x" * 64, b""), (b"x" * 64, b"curta"), (b"x", b"x" * 32)],
    )
    def test_entradas_malformadas_dao_false(self, assinatura, chave):
        assert verify(b"dado", assinatura, chave) is False

    def test_base64_invalido(self):
        assert verify_b64(b"d", "!!!", b"x" * 32) is False

    @pytest.mark.skipif(os.name == "nt", reason="permissões POSIX")
    def test_n25_chave_privada_com_permissao_0600(self, tmp_path):
        par = generate_keypair()
        priv, pub = tmp_path / "priv.key", tmp_path / "pub.key"
        priv.write_text("antigo")
        priv.chmod(0o644)  # arquivo pré-existente com permissão aberta
        save_keypair(par, str(priv), str(pub))
        assert stat.S_IMODE(os.stat(priv).st_mode) == 0o600
        assert load_public_key(str(pub)) == par.public_key
