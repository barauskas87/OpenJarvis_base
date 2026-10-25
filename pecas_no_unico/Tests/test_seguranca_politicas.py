"""Capacidades (RBAC), limitador de taxa, SSRF e arquivos sensíveis."""

from __future__ import annotations

import os
import socket
import threading

import pytest

from apoio import FerramentaEco
from openjarvis.security.capabilities import (
    Capability,
    CapabilityPolicy,
    canonical_tool_capabilities,
)
from openjarvis.security.file_policy import is_sensitive_file
from openjarvis.security.rate_limiter import RateLimitConfig, RateLimiter, TokenBucket
from openjarvis.security.ssrf import check_ssrf
from openjarvis.tools._stubs import ToolSpec
from openjarvis.tools.mcp_adapter import MCPToolAdapter


@pytest.mark.funcao
class TestCapacidades:
    def test_padrao_nega(self):
        assert CapabilityPolicy().check("a", "file:read", "x") is False

    def test_permissiva_libera(self):
        assert CapabilityPolicy.permissiva().check("a", "code:execute", "x") is True

    def test_concessao_basica(self):
        p = CapabilityPolicy()
        p.grant("a", "file:read")
        assert p.check("a", "file:read", "file_read")
        assert not p.check("a", "file:write", "file_write")

    def test_negacao_explicita_sempre_vence(self):
        p = CapabilityPolicy()
        p.grant("a", "*")
        p.deny("a", "code:execute")
        assert p.check("a", "file:read", "x")
        assert not p.check("a", "code:execute", "shell_exec")

    def test_padrao_de_recurso(self):
        p = CapabilityPolicy()
        p.grant("a", "file:*", pattern="file_read")
        assert p.check("a", "file:read", "file_read")
        assert not p.check("a", "file:read", "outra")
        assert not p.check("a", "file:read", "")

    def test_agente_curinga_so_vale_sem_politica_propria(self):
        p = CapabilityPolicy()
        p.grant("_default", "file:read")
        assert p.check("novo", "file:read", "x")
        p.grant("especial", "network:fetch")
        assert not p.check("especial", "file:read", "x")  # não herda do curinga

    def test_aceita_enum_como_capacidade(self):
        p = CapabilityPolicy()
        p.grant("a", Capability.FILE_READ.value)
        assert p.check("a", Capability.FILE_READ, "x")

    def test_salvar_e_carregar(self, tmp_path):
        p = CapabilityPolicy()
        p.grant("a", "file:read", "file_read")
        p.deny("a", "code:execute")
        arq = tmp_path / "politica.json"
        p.save(arq)
        q = CapabilityPolicy(policy_path=str(arq))
        assert q.check("a", "file:read", "file_read")
        assert not q.check("a", "code:execute", "x")

    def test_piso_canonico_de_ferramentas_nativas(self):
        eco = FerramentaEco("shell_exec")
        # fora de openjarvis.tools.* não é "nativa": nome privilegiado mantém o piso
        assert canonical_tool_capabilities(eco)

    def test_mcp_nao_se_passa_por_ferramenta_segura(self):
        class ClienteFalso:  # noqa: D101
            def call_tool(self, *a, **k):
                return {}

        adaptador = MCPToolAdapter(
            ClienteFalso(), ToolSpec(name="calculator", description="x"), servidor="s"
        )
        assert canonical_tool_capabilities(adaptador) == [Capability.TOOL_INVOKE]
        assert adaptador.spec.name == "mcp__s__calculator"


@pytest.mark.estabilidade
class TestCapacidadesEstabilidade:
    @pytest.mark.parametrize(
        "conteudo",
        [
            "{",
            "[]",
            '{"agents": "x"}',
            '{"agents": [1]}',
            '{"agents": [{"agent_id": ""}]}',
            '{"agents": [{"agent_id": "a", "grants": [{"capability": ""}]}]}',
            '{"agents": [{"agent_id": "a", "deny": [3]}]}',
        ],
    )
    def test_politica_malformada_levanta(self, tmp_path, conteudo):
        arq = tmp_path / "p.json"
        arq.write_text(conteudo)
        with pytest.raises(Exception):
            CapabilityPolicy(policy_path=str(arq))


@pytest.mark.interferencia
class TestCapacidadesInterferencia:
    def test_concessoes_e_checagens_simultaneas(self):
        p = CapabilityPolicy()
        erros = []

        def escreve(i):
            try:
                for n in range(100):
                    p.grant(f"ag{i}", "file:read")
                    p.deny(f"ag{i}", "x:y")
            except Exception as exc:  # noqa: BLE001
                erros.append(exc)

        def le(i):
            try:
                for _ in range(300):
                    p.check(f"ag{i}", "file:read", "r")
            except Exception as exc:  # noqa: BLE001
                erros.append(exc)

        ts = [threading.Thread(target=escreve, args=(i,)) for i in range(4)]
        ts += [threading.Thread(target=le, args=(i,)) for i in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert not erros


@pytest.mark.funcao
class TestRateLimiter:
    def test_rajada_e_espera(self):
        relogio = [0.0]
        rl = RateLimiter(
            RateLimitConfig(requests_per_minute=60, burst_size=3),
            relogio=lambda: relogio[0],
        )
        assert [rl.check("k")[0] for _ in range(3)] == [True, True, True]
        ok, espera = rl.check("k")
        assert ok is False and espera == pytest.approx(1.0)
        relogio[0] += 1.0
        assert rl.check("k")[0] is True

    def test_chaves_independentes_e_reset(self):
        rl = RateLimiter(RateLimitConfig(requests_per_minute=1, burst_size=1))
        assert rl.check("a")[0] and rl.check("b")[0]
        assert not rl.check("a")[0]
        rl.reset("a")
        assert rl.check("a")[0]
        rl.reset()
        assert rl.check("b")[0]

    def test_desabilitado_libera(self):
        rl = RateLimiter(RateLimitConfig(enabled=False, burst_size=1))
        assert all(rl.check("k")[0] for _ in range(50))

    def test_teto_de_baldes(self):
        rl = RateLimiter(RateLimitConfig(max_buckets=10))
        for i in range(100):
            rl.check(f"k{i}")
        assert len(rl._buckets) <= 10  # noqa: SLF001

    def test_parametros_invalidos(self):
        with pytest.raises(ValueError):
            TokenBucket(rate=0, capacity=1)
        with pytest.raises(ValueError):
            TokenBucket(rate=1, capacity=0)

    def test_concorrencia_nao_passa_do_limite(self):
        rl = RateLimiter(RateLimitConfig(requests_per_minute=1, burst_size=5))
        permitidos = []
        trava = threading.Lock()

        def trabalho():
            for _ in range(20):
                ok, _ = rl.check("k")
                if ok:
                    with trava:
                        permitidos.append(1)

        ts = [threading.Thread(target=trabalho) for _ in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert len(permitidos) <= 6  # 5 da rajada + no máx. 1 de recarga


@pytest.mark.funcao
class TestSSRF:
    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/",
            "http://localhost:8080/",
            "http://169.254.169.254/latest/meta-data",
            "http://metadata.google.internal/",
            "http://2130706433/",  # 127.0.0.1 em decimal
            "http://0x7f000001/",  # hexadecimal
            "http://127.1/",  # forma curta
            "http://[::1]/",
            "http://[::ffff:127.0.0.1]/",
            "http://[::ffff:169.254.169.254]/",
            "http://10.1.2.3/",
            "http://192.168.0.5/",
            "http://100.64.0.1/",  # CGNAT
            "file:///etc/passwd",
            "ftp://exemplo.com/x",
            "gopher://exemplo.com/",
            "http:///sem-host",
            "",
        ],
    )
    def test_bloqueia(self, url):
        assert check_ssrf(url)

    def test_permite_ip_publico_literal(self):
        assert check_ssrf("https://93.184.216.34/x") is None

    def test_dns_que_falha_bloqueia(self, monkeypatch):
        def falha(*a, **k):
            raise socket.gaierror("sem dns")

        monkeypatch.setattr(socket, "getaddrinfo", falha)
        assert "fail-closed" in check_ssrf("https://nao-existe.example/")

    def test_dns_para_ip_privado_bloqueia(self, monkeypatch):
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *a, **k: [(2, 1, 6, "", ("10.0.0.7", 0))],
        )
        assert check_ssrf("https://interno.example/")

    def test_dns_para_ip_publico_permite(self, monkeypatch):
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))],
        )
        assert check_ssrf("https://publico.example/") is None

    def test_ssrf_fail_open_so_com_variavel_explicita(self, monkeypatch):
        def falha(*a, **k):
            raise socket.gaierror("x")

        monkeypatch.setattr(socket, "getaddrinfo", falha)
        monkeypatch.setenv("OPENJARVIS_SSRF_FAIL_OPEN", "1")
        assert check_ssrf("https://nao-existe.example/") is None


@pytest.mark.funcao
class TestArquivosSensiveis:
    @pytest.mark.parametrize(
        "nome",
        [
            ".env",
            ".ENV",
            ".env.local",
            "chave.pem",
            "CHAVE.KEY",
            "id_rsa",
            "id_ecdsa",
            ".vault_key",
            ".npmrc",
            "credentials",
            "senhas.txt",
            "client_secret_123.json",
            "banco.kdbx",
        ],
    )
    def test_nomes_sensiveis(self, nome, tmp_path):
        assert is_sensitive_file(tmp_path / nome)

    @pytest.mark.parametrize("nome", ["notas.txt", "README.md", "dados.csv", "env.py"])
    def test_nomes_comuns(self, nome, tmp_path):
        assert not is_sensitive_file(tmp_path / nome)

    def test_diretorios_protegidos(self, tmp_path):
        assert is_sensitive_file(tmp_path / ".ssh" / "known_hosts")
        assert is_sensitive_file(tmp_path / ".aws" / "config")

    def test_tudo_dentro_do_estado_do_no(self, estado_isolado):
        assert is_sensitive_file(estado_isolado / "config.toml")
        assert is_sensitive_file(estado_isolado / "connectors" / "google.json")
        assert is_sensitive_file(estado_isolado / "traces.db")

    @pytest.mark.skipif(os.name == "nt", reason="symlink exige privilégio no Windows")
    def test_symlink_nao_esconde_nome_sensivel(self, tmp_path):
        alvo = tmp_path / "id_rsa"
        alvo.write_text("x")
        ligacao = tmp_path / "inocente.txt"
        ligacao.symlink_to(alvo)
        assert is_sensitive_file(ligacao)

    def test_ciclo_de_symlink_nao_trava(self, tmp_path):
        if os.name == "nt":
            pytest.skip("symlink")
        a, b = tmp_path / "a", tmp_path / "b"
        a.symlink_to(b)
        b.symlink_to(a)
        assert is_sensitive_file(a) in (True, False)
