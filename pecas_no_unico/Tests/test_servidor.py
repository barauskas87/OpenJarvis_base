"""Testes da API do Nó (servidor para o app Android) nas 6 dimensões."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import List, Tuple

import pytest
from fastapi.testclient import TestClient

from apoio import MotorRoteirizado
from openjarvis.agents.native_react import NativeReActAgent
from openjarvis.servidor.aplicacao import criar_aplicacao
from openjarvis.servidor.autenticacao import (
    AutenticadorToken,
    gerar_token,
    hash_token,
)
from openjarvis.servidor.conversador import ConversadorAgente, ResultadoConversa
from openjarvis.servidor.historico import HistoricoDeConversas
from openjarvis.servidor.modelos import (
    PedidoConversa,
    RespostaConversa,
    RespostaErro,
    RespostaSaude,
)
from openjarvis.servidor.principal import (
    ler_hashes,
    montar_parser,
    principal,
    validar_exposicao,
)

CONTRATO = Path(__file__).resolve().parents[2] / "contrato"


class ConversadorEco:
    """Responde repetindo a mensagem e registra o que recebeu."""

    def __init__(self) -> None:
        self.recebidos: List[Tuple[str, List[Tuple[str, str]]]] = []

    def conversar(self, mensagem, historico):
        self.recebidos.append((mensagem, list(historico)))
        return ResultadoConversa(resposta=f"eco:{mensagem}", turnos=1)


@pytest.fixture
def token():
    return gerar_token()


@pytest.fixture
def auth(token):
    return AutenticadorToken([hash_token(token)])


def cab(token):
    return {"Authorization": f"Bearer {token}"}


def montar(conversador, auth, **kw):
    return TestClient(criar_aplicacao(conversador, auth, **kw))


# ---------------------------------------------------------------- função


@pytest.mark.funcao
class TestAutenticacaoFuncao:
    def test_token_tem_prefixo_e_entropia(self):
        a, b = gerar_token(), gerar_token()
        assert a != b and a.startswith("nu_") and len(a) >= 40

    def test_hash_estavel_e_hex(self):
        assert hash_token("x") == hash_token("x")
        assert len(hash_token("x")) == 64

    def test_aceita_so_o_token_certo(self, token, auth):
        assert auth.verificar(token)
        assert not auth.verificar(token + "x")
        assert not auth.verificar("")
        assert not auth.verificar(None)

    def test_varios_tokens(self):
        t1, t2 = gerar_token(), gerar_token()
        a = AutenticadorToken([hash_token(t1), hash_token(t2)])
        assert a.verificar(t1) and a.verificar(t2)
        assert a.identificar(t1) != a.identificar(t2)

    @pytest.mark.parametrize("ruim", ["abc", "g" * 64, "a" * 63, ""])
    def test_hash_malformado_recusado(self, ruim):
        with pytest.raises(ValueError):
            AutenticadorToken([ruim])

    def test_lista_vazia_recusada(self):
        with pytest.raises(ValueError):
            AutenticadorToken([])


@pytest.mark.funcao
class TestApiFuncao:
    def test_saude_sem_token(self, auth):
        r = montar(ConversadorEco(), auth).get("/v1/saude")
        assert r.status_code == 200
        assert RespostaSaude(**r.json()).status == "ok"

    def test_conversar_ok(self, token, auth):
        r = montar(ConversadorEco(), auth).post(
            "/v1/conversar", json={"mensagem": "oi"}, headers=cab(token)
        )
        corpo = RespostaConversa(**r.json())
        assert r.status_code == 200
        assert corpo.resposta == "eco:oi" and corpo.turnos == 1
        assert len(corpo.conversa_id) >= 8

    def test_historico_na_segunda_chamada(self, token, auth):
        eco = ConversadorEco()
        c = montar(eco, auth)
        cid = c.post(
            "/v1/conversar", json={"mensagem": "um"}, headers=cab(token)
        ).json()["conversa_id"]
        c.post(
            "/v1/conversar",
            json={"mensagem": "dois", "conversa_id": cid},
            headers=cab(token),
        )
        assert eco.recebidos[1][1] == [("um", "eco:um")]

    @pytest.mark.parametrize(
        "cabecalho",
        [
            {},
            {"Authorization": "Bearer errado"},
            {"Authorization": "Basic abc"},
            {"Authorization": "Bearer"},
            {"Authorization": "bearer "},
        ],
    )
    def test_sem_token_valido_401(self, auth, cabecalho):
        r = montar(ConversadorEco(), auth).post(
            "/v1/conversar", json={"mensagem": "oi"}, headers=cabecalho
        )
        assert r.status_code == 401
        assert r.headers["www-authenticate"] == "Bearer"
        assert r.json()["erro"] == "nao_autorizado"

    def test_esquema_bearer_sem_diferenca_de_caixa(self, token, auth):
        r = montar(ConversadorEco(), auth).post(
            "/v1/conversar",
            json={"mensagem": "oi"},
            headers={"Authorization": f"BEARER {token}"},
        )
        assert r.status_code == 200

    def test_segredo_na_resposta_e_mascarado(self, token, auth):
        class Vaza:
            def conversar(self, m, h):
                return ResultadoConversa("a chave é sk-ant-" + "A" * 30, 1)

        r = montar(Vaza(), auth).post(
            "/v1/conversar", json={"mensagem": "oi"}, headers=cab(token)
        )
        assert "sk-ant-AAAA" not in r.text and "REDACTED" in r.json()["resposta"]

    def test_cabecalhos_de_seguranca(self, auth):
        r = montar(ConversadorEco(), auth).get("/v1/saude")
        assert r.headers["cache-control"] == "no-store"
        assert r.headers["x-content-type-options"] == "nosniff"

    def test_documentacao_nao_exposta(self, auth):
        c = montar(ConversadorEco(), auth)
        for caminho in ("/docs", "/redoc", "/openapi.json"):
            assert c.get(caminho).status_code == 404

    @pytest.mark.parametrize(
        "corpo",
        [
            {"mensagem": ""},
            {"mensagem": "   \n\t"},
            {"mensagem": "oi", "extra": 1},
            {"mensagem": "oi", "conversa_id": "../etc"},
            {"mensagem": "oi", "conversa_id": "a" * 65},
            {"mensagem": 5},
            {},
        ],
    )
    def test_pedido_invalido_422(self, token, auth, corpo):
        r = montar(ConversadorEco(), auth).post(
            "/v1/conversar", json=corpo, headers=cab(token)
        )
        assert r.status_code == 422 and r.json()["erro"] == "pedido_invalido"

    def test_metodo_errado(self, token, auth):
        assert (
            montar(ConversadorEco(), auth)
            .get("/v1/conversar", headers=cab(token))
            .status_code
            == 405
        )


@pytest.mark.funcao
class TestLinhaDeComando:
    def test_gerar_token_imprime_token_e_hash(self, capsys):
        assert principal(["gerar-token"]) == 0
        saida = capsys.readouterr().out
        token = next(p for p in saida.split() if p.startswith("nu_"))
        hash_ = next(p for p in saida.split() if len(p) == 64)
        assert hash_token(token) == hash_

    def test_ler_hashes_arquivo_e_ambiente(self, tmp_path):
        arq = tmp_path / "t.txt"
        arq.write_text("a\n\nb\n", encoding="utf-8")
        assert ler_hashes(str(arq), "c, d") == ["a", "b", "c", "d"]
        assert ler_hashes(None, None) == []

    @pytest.mark.parametrize(
        "host,cert,chave,proxy,recusa",
        [
            ("127.0.0.1", None, None, False, False),
            ("localhost", None, None, False, False),
            ("0.0.0.0", None, None, False, True),
            ("192.168.0.5", None, None, False, True),
            ("0.0.0.0", "c.pem", "k.pem", False, False),
            ("0.0.0.0", None, None, True, False),
            ("127.0.0.1", "c.pem", None, False, True),
        ],
    )
    def test_exposicao(self, host, cert, chave, proxy, recusa):
        assert bool(validar_exposicao(host, cert, chave, proxy)) is recusa

    def test_servir_recusa_exposicao_sem_tls(self, capsys):
        codigo = principal(["servir", "--modelo", "m", "--host", "0.0.0.0"])
        assert codigo == 2 and "TLS" in capsys.readouterr().err

    def test_servir_recusa_sem_tokens(self, capsys, monkeypatch):
        monkeypatch.delenv("NO_UNICO_TOKEN_HASHES", raising=False)
        assert principal(["servir", "--modelo", "m"]) == 2

    def test_modelo_obrigatorio(self):
        with pytest.raises(SystemExit):
            montar_parser().parse_args(["servir"])


@pytest.mark.funcao
class TestContrato:
    """Os mesmos arquivos de ``contrato/`` são lidos pelos testes do cliente Kotlin."""

    def _ler(self, nome):
        return json.loads((CONTRATO / nome).read_text(encoding="utf-8"))

    def test_pedidos_do_contrato_sao_aceitos(self):
        PedidoConversa(**self._ler("pedido_conversar.json"))
        PedidoConversa(**self._ler("pedido_conversar_minimo.json"))

    def test_respostas_do_contrato_sao_validas(self):
        RespostaConversa(**self._ler("resposta_conversar.json"))
        RespostaSaude(**self._ler("resposta_saude.json"))
        RespostaErro(**self._ler("resposta_erro.json"))

    def test_esquema_nao_mudou_sem_avisar(self, auth):
        """Se este teste falha, o contrato mudou: atualize o cliente Kotlin."""
        atual = criar_aplicacao(ConversadorEco(), auth).openapi()
        esperado = self._ler("openapi.json")
        assert atual == esperado


# ----------------------------------------------------------- estabilidade


@pytest.mark.estabilidade
class TestApiEstabilidade:
    def test_corpo_grande_pelo_cabecalho_413(self, token, auth):
        c = montar(ConversadorEco(), auth, tamanho_max_corpo=1000)
        r = c.post(
            "/v1/conversar",
            content=b"x" * 5000,
            headers={**cab(token), "Content-Type": "application/json"},
        )
        assert r.status_code == 413

    def test_corpo_grande_em_pedacos_sem_content_length_413(self, token, auth):
        c = montar(ConversadorEco(), auth, tamanho_max_corpo=1000)

        def pedacos():
            for _ in range(50):
                yield b"x" * 100

        r = c.post(
            "/v1/conversar",
            content=pedacos(),
            headers={**cab(token), "Content-Type": "application/json"},
        )
        assert r.status_code == 413

    def test_content_length_invalido_400(self, token, auth):
        r = montar(ConversadorEco(), auth).post(
            "/v1/conversar",
            content=b"{}",
            headers={**cab(token), "Content-Length": "abc"},
        )
        assert r.status_code in (400, 422)

    @pytest.mark.parametrize(
        "corpo", [b"", b"{", b"nao json", b"\xff\xfe", b"[]", b"null", b"1"]
    )
    def test_corpo_malformado_nunca_vira_500(self, token, auth, corpo):
        r = montar(ConversadorEco(), auth).post(
            "/v1/conversar",
            content=corpo,
            headers={**cab(token), "Content-Type": "application/json"},
        )
        assert r.status_code in (400, 422)

    def test_erro_interno_nao_vaza_detalhe(self, token, auth):
        class Quebra:
            def conversar(self, m, h):
                raise RuntimeError("senha-do-banco=hunter2 /home/dono/segredo")

        r = montar(Quebra(), auth).post(
            "/v1/conversar", json={"mensagem": "oi"}, headers=cab(token)
        )
        assert r.status_code == 500
        assert "hunter2" not in r.text and "/home" not in r.text
        assert r.json()["erro"] == "falha_interna"

    def test_erro_de_validacao_nao_repete_o_que_foi_enviado(self, token, auth):
        r = montar(ConversadorEco(), auth).post(
            "/v1/conversar",
            json={"mensagem": "oi", "campo_secreto": "VALOR-SENSIVEL-123"},
            headers=cab(token),
        )
        assert r.status_code == 422
        assert "VALOR-SENSIVEL-123" not in r.text

    def test_limites_exatos_da_mensagem(self, token, auth):
        c = montar(ConversadorEco(), auth)
        assert (
            c.post(
                "/v1/conversar", json={"mensagem": "a" * 8000}, headers=cab(token)
            ).status_code
            == 200
        )
        assert (
            c.post(
                "/v1/conversar", json={"mensagem": "a" * 8001}, headers=cab(token)
            ).status_code
            == 422
        )

    def test_unicode_e_emoji(self, token, auth):
        r = montar(ConversadorEco(), auth).post(
            "/v1/conversar", json={"mensagem": "olá 🌎 日本語"}, headers=cab(token)
        )
        assert r.json()["resposta"] == "eco:olá 🌎 日本語"

    def test_token_gigante_nao_quebra(self, auth):
        r = montar(ConversadorEco(), auth).post(
            "/v1/conversar",
            json={"mensagem": "oi"},
            headers={"Authorization": "Bearer " + "a" * 100_000},
        )
        assert r.status_code in (401, 431)

    def test_excesso_de_falhas_vira_429_sem_bloquear_token_valido(self, token, auth):
        c = montar(ConversadorEco(), auth, falhas_por_minuto=3)
        codigos = [
            c.post(
                "/v1/conversar",
                json={"mensagem": "x"},
                headers={"Authorization": "Bearer ruim"},
            ).status_code
            for _ in range(6)
        ]
        assert codigos[:3] == [401, 401, 401] and 429 in codigos[3:]
        ok = c.post("/v1/conversar", json={"mensagem": "x"}, headers=cab(token))
        assert ok.status_code == 200

    def test_limite_de_uso_por_token_com_retry_after(self, token, auth):
        c = montar(
            ConversadorEco(),
            auth,
            requisicoes_por_minuto=6,
            rajada=2,
            relogio=lambda: 0.0,
        )
        r = [
            c.post("/v1/conversar", json={"mensagem": "x"}, headers=cab(token))
            for _ in range(3)
        ]
        assert [x.status_code for x in r] == [200, 200, 429]
        assert int(r[2].headers["retry-after"]) >= 1

    def test_timeout_devolve_504_e_a_vaga_so_volta_quando_o_trabalho_acaba(
        self, token, auth
    ):
        solto = threading.Event()

        class Lento:
            def conversar(self, m, h):
                solto.wait(5)
                return ResultadoConversa("fim", 1)

        with TestClient(
            criar_aplicacao(Lento(), auth, tempo_limite_s=0.2, max_simultaneas=1)
        ) as c:
            r1 = c.post("/v1/conversar", json={"mensagem": "a"}, headers=cab(token))
            assert r1.status_code == 504
            # a thread ainda roda: a vaga continua ocupada
            r2 = c.post("/v1/conversar", json={"mensagem": "b"}, headers=cab(token))
            assert r2.status_code == 503 and "retry-after" in r2.headers
            solto.set()
            for _ in range(50):
                time.sleep(0.05)
                r3 = c.post("/v1/conversar", json={"mensagem": "c"}, headers=cab(token))
                if r3.status_code != 503:
                    break
            assert r3.status_code in (200, 504)


# -------------------------------------------------------------- integração


@pytest.mark.integracao
class TestIntegracaoAgenteReal:
    def _app(self, auth, respostas):
        motor = MotorRoteirizado(respostas)
        conv = ConversadorAgente(lambda: NativeReActAgent(motor, "m", tools=[]))
        return motor, montar(conv, auth)

    def test_pedido_passa_pelo_agente_real(self, token, auth):
        motor, c = self._app(auth, ["Final Answer: Olá do agente"])
        r = c.post("/v1/conversar", json={"mensagem": "oi"}, headers=cab(token))
        assert r.status_code == 200
        assert "Olá do agente" in r.json()["resposta"]
        assert len(motor.chamadas) == 1

    def test_historico_chega_ao_modelo(self, token, auth):
        motor, c = self._app(auth, ["Final Answer: primeira", "Final Answer: segunda"])
        cid = c.post(
            "/v1/conversar", json={"mensagem": "pergunta-um"}, headers=cab(token)
        ).json()["conversa_id"]
        c.post(
            "/v1/conversar",
            json={"mensagem": "pergunta-dois", "conversa_id": cid},
            headers=cab(token),
        )
        texto = " ".join(str(m.content) for m in motor.chamadas[1])
        assert "pergunta-um" in texto and "primeira" in texto

    def test_ferramenta_inexistente_nao_executa_nada(self, token, auth):
        _, c = self._app(
            auth,
            [
                'Thought: vou rodar\nAction: shell_exec\nAction Input: {"command": "id"}',
                "Final Answer: não consegui",
            ],
        )
        r = c.post("/v1/conversar", json={"mensagem": "rode id"}, headers=cab(token))
        assert r.status_code == 200 and "uid=" not in r.json()["resposta"]

    def test_resposta_do_modelo_com_segredo_sai_mascarada(self, token, auth):
        _, c = self._app(auth, ["Final Answer: use AKIAABCDEFGHIJKLMNOP"])
        r = c.post("/v1/conversar", json={"mensagem": "chave?"}, headers=cab(token))
        assert "AKIAABCDEFGHIJKLMNOP" not in r.text


# ------------------------------------------------------------ interferência


@pytest.mark.interferencia
class TestInterferencia:
    def test_tokens_diferentes_nao_leem_a_conversa_um_do_outro(self):
        ta, tb = gerar_token(), gerar_token()
        eco = ConversadorEco()
        c = montar(eco, AutenticadorToken([hash_token(ta), hash_token(tb)]))
        c.post(
            "/v1/conversar",
            json={"mensagem": "segredo-de-A", "conversa_id": "x"},
            headers=cab(ta),
        )
        c.post(
            "/v1/conversar",
            json={"mensagem": "oi", "conversa_id": "x"},
            headers=cab(tb),
        )
        assert eco.recebidos[1][1] == []

    def test_limite_de_um_token_nao_afeta_outro(self):
        ta, tb = gerar_token(), gerar_token()
        c = montar(
            ConversadorEco(),
            AutenticadorToken([hash_token(ta), hash_token(tb)]),
            requisicoes_por_minuto=6,
            rajada=1,
            relogio=lambda: 0.0,
        )
        assert (
            c.post("/v1/conversar", json={"mensagem": "x"}, headers=cab(ta)).status_code
            == 200
        )
        assert (
            c.post("/v1/conversar", json={"mensagem": "x"}, headers=cab(ta)).status_code
            == 429
        )
        assert (
            c.post("/v1/conversar", json={"mensagem": "x"}, headers=cab(tb)).status_code
            == 200
        )

    def test_clientes_simultaneos_recebem_a_propria_resposta(self, token, auth):
        c = montar(
            ConversadorEco(),
            auth,
            requisicoes_por_minuto=6000,
            rajada=1000,
            max_simultaneas=16,
        )
        erros, saida = [], {}

        def cliente(i):
            try:
                with TestClient(c.app) as cl:
                    for j in range(5):
                        msg = f"m{i}-{j}"
                        r = cl.post(
                            "/v1/conversar",
                            json={"mensagem": msg, "conversa_id": f"c{i}"},
                            headers=cab(token),
                        )
                        if r.json().get("resposta") != f"eco:{msg}":
                            erros.append((msg, r.text))
                    saida[i] = True
            except Exception as exc:  # noqa: BLE001
                erros.append(exc)

        fios = [threading.Thread(target=cliente, args=(i,)) for i in range(12)]
        [f.start() for f in fios]
        [f.join(30) for f in fios]
        assert not erros and len(saida) == 12

    def test_historico_concorrente_nao_corrompe(self):
        h = HistoricoDeConversas(max_conversas=50, max_pares=5)

        def escreve(i):
            for j in range(200):
                h.registrar("d", f"c{j % 80}", f"u{i}", f"r{i}")
                h.obter("d", f"c{j % 80}")

        fios = [threading.Thread(target=escreve, args=(i,)) for i in range(8)]
        [f.start() for f in fios]
        [f.join(30) for f in fios]
        assert len(h) <= 50


# --------------------------------------------------------------- desempenho


@pytest.mark.desempenho
class TestDesempenho:
    def test_200_pedidos_em_poucos_segundos(self, token, auth):
        with TestClient(
            criar_aplicacao(
                ConversadorEco(), auth, requisicoes_por_minuto=60000, rajada=10000
            )
        ) as c:
            t0 = time.perf_counter()
            for i in range(200):
                assert (
                    c.post(
                        "/v1/conversar", json={"mensagem": f"m{i}"}, headers=cab(token)
                    ).status_code
                    == 200
                )
            assert time.perf_counter() - t0 < 20

    def test_verificacao_de_token_e_rapida_com_muitos_tokens(self):
        tokens = [gerar_token() for _ in range(200)]
        a = AutenticadorToken([hash_token(t) for t in tokens])
        t0 = time.perf_counter()
        for _ in range(500):
            assert a.verificar(tokens[-1])
        assert time.perf_counter() - t0 < 5

    def test_historico_respeita_o_teto_de_memoria(self):
        h = HistoricoDeConversas(max_conversas=100, max_pares=3)
        for i in range(5000):
            h.registrar("d", f"c{i}", "u", "r")
        assert len(h) == 100

    def test_corpo_no_teto_e_aceito_sem_demora(self, token, auth):
        c = montar(ConversadorEco(), auth)
        msg = "a" * 8000
        t0 = time.perf_counter()
        assert (
            c.post(
                "/v1/conversar", json={"mensagem": msg}, headers=cab(token)
            ).status_code
            == 200
        )
        assert time.perf_counter() - t0 < 2


# ------------------------------------------------------------ recursividade


@pytest.mark.recursividade
class TestRecursividade:
    @pytest.mark.parametrize("profundidade", [100, 10_000, 200_000])
    def test_json_muito_aninhado_vira_400_ou_422(self, token, auth, profundidade):
        corpo = ("[" * profundidade + "]" * profundidade).encode()
        r = montar(ConversadorEco(), auth).post(
            "/v1/conversar",
            content=corpo,
            headers={**cab(token), "Content-Type": "application/json"},
        )
        assert r.status_code in (400, 413, 422)

    def test_objeto_aninhado_no_campo_e_recusado(self, token, auth):
        aninhado = {"a": {"a": {"a": 1}}}
        r = montar(ConversadorEco(), auth).post(
            "/v1/conversar", json={"mensagem": aninhado}, headers=cab(token)
        )
        assert r.status_code == 422

    def test_conversa_longa_guarda_so_os_ultimos_pares(self, token, auth):
        eco = ConversadorEco()
        c = montar(
            eco,
            auth,
            historico=HistoricoDeConversas(max_pares=3),
            requisicoes_por_minuto=6000,
            rajada=1000,
        )
        for i in range(40):
            c.post(
                "/v1/conversar",
                json={"mensagem": f"m{i}", "conversa_id": "x"},
                headers=cab(token),
            )
        assert len(eco.recebidos[-1][1]) == 3
        assert eco.recebidos[-1][1][-1][0] == "m38"

    def test_agente_em_laco_de_ferramenta_termina(self, token, auth):
        repete = "Thought: de novo\nAction: nada\nAction Input: {}"
        motor = MotorRoteirizado([repete] * 40)
        conv = ConversadorAgente(
            lambda: NativeReActAgent(motor, "m", tools=[], max_turns=4)
        )
        r = montar(conv, auth).post(
            "/v1/conversar", json={"mensagem": "oi"}, headers=cab(token)
        )
        assert r.status_code == 200 and len(motor.chamadas) <= 5
