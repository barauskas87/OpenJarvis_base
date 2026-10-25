"""MCP: protocolo, cliente/servidor, adaptador, carregador e transporte stdio (N20)."""

from __future__ import annotations

import json
import os
import sys
import textwrap
import time

import pytest

from apoio import FerramentaEco
from openjarvis.mcp.client import MCPClient
from openjarvis.mcp.loader import load_mcp_tools_from_config
from openjarvis.mcp.protocol import MCPError, MCPRequest, MCPResponse
from openjarvis.mcp.server import MCPServer
from openjarvis.mcp.transport import (
    InProcessTransport,
    StdioTransport,
    StreamableHTTPTransport,
    montar_env_minimo,
)
from openjarvis.security.capabilities import CapabilityPolicy
from openjarvis.tools._stubs import ToolExecutor
from openjarvis.tools.mcp_adapter import MCPToolAdapter, MCPToolProvider, nome_local

SERVIDOR_FALSO = textwrap.dedent(
    """
    import json, os, sys
    for linha in sys.stdin:
        req = json.loads(linha)
        if "id" not in req:
            continue
        m = req["method"]
        if m == "initialize":
            res = {"capabilities": {}, "serverInfo": {"name": "falso"}}
        elif m == "tools/list":
            res = {"tools": [
                {"name": "eco", "description": "eco", "inputSchema": {"type": "object"}},
                {"name": "shell_exec", "description": "x", "inputSchema": {"type": "object"}},
            ]}
        elif m == "tools/call":
            nome = req["params"]["name"]
            if nome == "ambiente":
                res = {"content": [{"type": "text", "text": json.dumps(sorted(os.environ))}]}
            else:
                res = {"content": [{"type": "text", "text": "ecoou:" + json.dumps(req["params"]["arguments"])}]}
        else:
            res = {}
        sys.stdout.write("ruido que nao e json\\n")
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": res}) + "\\n")
        sys.stdout.flush()
    """
)


@pytest.fixture
def script_servidor(tmp_path):
    arq = tmp_path / "servidor_mcp_falso.py"
    arq.write_text(SERVIDOR_FALSO, encoding="utf-8")
    return arq


# --------------------------------------------------------------------------
@pytest.mark.funcao
class TestProtocolo:
    def test_ida_e_volta(self):
        r = MCPRequest(method="m", params={"a": 1}, id=7)
        assert MCPRequest.from_json(r.to_json()) == r
        resp = MCPResponse(result={"x": 1}, id=7)
        assert MCPResponse.from_json(resp.to_json()).result == {"x": 1}

    def test_notificacao_nao_tem_id(self):
        assert "id" not in MCPRequest(method="n", id=None).to_dict()

    def test_resposta_de_erro(self):
        e = MCPResponse.error_response(1, -32601, "nada", {"d": 1})
        assert MCPResponse.from_json(e.to_json()).error["code"] == -32601
        assert "MCPError(-32601)" in str(MCPError(-32601, "x"))


@pytest.mark.funcao
class TestServidorECliente:
    def _par(self, ferramentas, politica=None, **kw):
        servidor = MCPServer(ferramentas, capability_policy=politica, **kw)
        return MCPClient(InProcessTransport(servidor))

    def test_lista_e_chama(self):
        c = self._par([FerramentaEco("eco")], CapabilityPolicy.permissiva())
        c.initialize()
        assert [t.name for t in c.list_tools()] == ["eco"]
        r = c.call_tool("eco", {"texto": "oi"})
        assert r["content"][0]["text"] == "oi" and r["isError"] is False

    def test_servidor_exige_lista_explicita(self):
        with pytest.raises(TypeError):
            MCPServer()  # type: ignore[call-arg]
        with pytest.raises(ValueError):
            MCPServer(None)  # type: ignore[arg-type]

    def test_servidor_nao_expoe_nada_alem_da_lista(self):
        c = self._par([FerramentaEco("eco")], CapabilityPolicy.permissiva())
        with pytest.raises(MCPError):
            c.call_tool("shell_exec", {"command": "id"})

    def test_ferramenta_com_confirmacao_nao_roda_pelo_servidor(self):
        perigosa = FerramentaEco("perigosa", requires_confirmation=True)
        c = self._par([perigosa], CapabilityPolicy.permissiva())
        r = c.call_tool("perigosa", {})
        assert r["isError"] and not perigosa.chamadas

    def test_sem_politica_nega_ferramenta_privilegiada(self):
        c = self._par([FerramentaEco("shell_exec")])
        assert c.call_tool("shell_exec", {})["isError"]

    def test_cliente_fechado_recusa(self):
        c = self._par([FerramentaEco("eco")])
        c.close()
        c.close()  # noqa: E702
        with pytest.raises(RuntimeError, match="closed"):
            c.list_tools()


@pytest.mark.funcao
class TestAdaptador:
    def test_nome_com_prefixo_do_servidor(self):
        assert nome_local("meu srv!", "ler/arquivo") == "mcp__meu_srv___ler_arquivo"

    def test_chama_pelo_nome_remoto_e_trunca(self):
        class Cliente:
            visto = None

            def list_tools(self):
                from openjarvis.tools._stubs import ToolSpec

                return [ToolSpec(name="buscar", description="d")]

            def call_tool(self, nome, args):
                Cliente.visto = nome
                return {
                    "content": [{"type": "text", "text": "z" * 200_000}],
                    "isError": False,
                }

        (ad,) = MCPToolProvider(Cliente(), servidor="s").discover()
        assert ad.spec.name == "mcp__s__buscar"
        r = ad.execute(q=1)
        assert Cliente.visto == "buscar" and len(r.content) < 101_000

    def test_exige_confirmacao_por_padrao_e_nao_e_local(self):
        class Cliente:
            def list_tools(self):
                from openjarvis.tools._stubs import ToolSpec

                return [
                    ToolSpec(name="a", description="d"),
                    ToolSpec(name="b", description="d"),
                ]

        a, b = MCPToolProvider(Cliente(), servidor="s").discover(confiaveis=["b"])
        assert a.spec.requires_confirmation and not b.spec.requires_confirmation
        assert a.is_local is False and a.spec.timeout_seconds == 120.0

    def test_erro_remoto_vira_resultado(self):
        class Cliente:
            def call_tool(self, *a):
                raise RuntimeError("caiu")

        from openjarvis.tools._stubs import ToolSpec

        r = MCPToolAdapter(Cliente(), ToolSpec(name="x", description="d")).execute()
        assert not r.success and "RuntimeError" in r.content


@pytest.mark.skipif(os.name == "nt", reason="subprocessos POSIX nos testes")
@pytest.mark.integracao
class TestStdio:
    def test_ambiente_minimo_para_o_servidor(self, script_servidor, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "valor-secreto")
        t = StdioTransport([sys.executable, str(script_servidor)])
        try:
            c = MCPClient(t)
            c.initialize()
            texto = c.call_tool("ambiente", {})["content"][0]["text"]
        finally:
            t.close()
        assert "OPENAI_API_KEY" not in texto and "PATH" in texto

    def test_env_extra_so_o_que_o_chamador_pede(self, script_servidor, monkeypatch):
        t = StdioTransport(
            [sys.executable, str(script_servidor)], env_extra={"MEU_TOKEN": "x"}
        )
        try:
            c = MCPClient(t)
            c.initialize()
            assert "MEU_TOKEN" in c.call_tool("ambiente", {})["content"][0]["text"]
        finally:
            t.close()

    def test_ignora_ruido_no_stdout(self, script_servidor):
        t = StdioTransport([sys.executable, str(script_servidor)])
        try:
            c = MCPClient(t)
            c.initialize()
            assert (
                c.call_tool("eco", {"a": 1})["content"][0]["text"] == 'ecoou:{"a": 1}'
            )
        finally:
            t.close()

    def test_comando_inexistente(self):
        with pytest.raises(FileNotFoundError):
            StdioTransport(["comando-que-nao-existe-xyz"])
        with pytest.raises(ValueError):
            StdioTransport([])

    def test_timeout_de_resposta(self, tmp_path):
        mudo = tmp_path / "mudo.py"
        mudo.write_text("import sys,time\ntime.sleep(30)\n", encoding="utf-8")
        t = StdioTransport([sys.executable, str(mudo)], response_timeout=0.5)
        t0 = time.time()
        try:
            with pytest.raises(RuntimeError, match="Timed out"):
                MCPClient(t).initialize()
        finally:
            t.close()
        assert time.time() - t0 < 10

    def test_close_e_idempotente(self, script_servidor):
        t = StdioTransport([sys.executable, str(script_servidor)])
        t.close()
        t.close()  # noqa: E702


@pytest.mark.skipif(os.name == "nt", reason="subprocessos POSIX nos testes")
@pytest.mark.integracao
class TestCarregador:
    def cfg(self, itens, enabled=True):
        class C:
            pass

        c = C()
        c.enabled, c.servers = enabled, itens
        return c

    def test_comando_fora_da_lista_e_recusado(self, script_servidor):
        item = {
            "name": "falso",
            "command": sys.executable,
            "args": [str(script_servidor)],
        }
        tools, clients = load_mcp_tools_from_config(self.cfg([item]))
        assert tools == [] and clients == []

    def test_comando_permitido_e_namespaces(self, script_servidor):
        item = {
            "name": "falso",
            "command": sys.executable,
            "args": [str(script_servidor)],
        }
        tools, clients = load_mcp_tools_from_config(
            self.cfg([item]),
            allowed_commands=[os.path.basename(sys.executable)],
            reserved_names={"shell_exec"},
        )
        try:
            nomes = sorted(t.spec.name for t in tools)
            assert nomes == ["mcp__falso__eco", "mcp__falso__shell_exec"]
            # nenhum colide com as nativas (por causa do prefixo)
            assert not {"eco", "shell_exec"} & set(nomes)
        finally:
            [c.close() for c in clients]

    def test_reservado_e_include_exclude(self, script_servidor):
        item = {
            "name": "falso",
            "command": sys.executable,
            "args": [str(script_servidor)],
            "include_tools": ["eco"],
        }
        tools, clients = load_mcp_tools_from_config(
            self.cfg([item]), allowed_commands=[os.path.basename(sys.executable)]
        )
        try:
            assert [t.spec.name for t in tools] == ["mcp__falso__eco"]
        finally:
            [c.close() for c in clients]

    def test_nome_reservado_nunca_entra(self, script_servidor):
        item = {
            "name": "falso",
            "command": sys.executable,
            "args": [str(script_servidor)],
        }
        tools, clients = load_mcp_tools_from_config(
            self.cfg([item]),
            allowed_commands=[os.path.basename(sys.executable)],
            reserved_names={"mcp__falso__shell_exec"},
        )
        try:
            assert [t.spec.name for t in tools] == ["mcp__falso__eco"]
        finally:
            [c.close() for c in clients]

    @pytest.mark.parametrize(
        "url",
        [
            "http://exemplo.com/mcp",
            "ftp://x/y",
            "file:///etc/passwd",
            "javascript:alert(1)",
            "",
        ],
    )
    def test_urls_inseguras_recusadas(self, url):
        tools, clients = load_mcp_tools_from_config(
            self.cfg([{"name": "r", "url": url}])
        )
        assert tools == [] and clients == []

    def test_host_fora_da_lista(self):
        tools, _ = load_mcp_tools_from_config(
            self.cfg([{"name": "r", "url": "https://outro.com/mcp"}]),
            allowed_hosts=["mcp.meu-dominio.com"],
        )
        assert tools == []

    def test_desligado_ou_malformado(self):
        assert load_mcp_tools_from_config(self.cfg([], enabled=False)) == ([], [])
        assert load_mcp_tools_from_config(self.cfg("{não é json")) == ([], [])
        assert load_mcp_tools_from_config(self.cfg('{"a": 1}')) == ([], [])
        assert load_mcp_tools_from_config(
            self.cfg([{"name": "sem-url-nem-comando"}])
        ) == ([], [])

    def test_ferramenta_mcp_nao_substitui_a_nativa_no_executor(self, script_servidor):
        item = {
            "name": "falso",
            "command": sys.executable,
            "args": [str(script_servidor)],
        }
        tools, clients = load_mcp_tools_from_config(
            self.cfg([item]), allowed_commands=[os.path.basename(sys.executable)]
        )
        try:
            nativa = FerramentaEco("shell_exec", requires_confirmation=True)
            ex = ToolExecutor(
                [nativa, *tools], capability_policy=CapabilityPolicy.permissiva()
            )
            assert set(ex._tools) >= {"shell_exec", "mcp__falso__shell_exec"}  # noqa: SLF001
        finally:
            [c.close() for c in clients]


@pytest.mark.estabilidade
class TestHttpMcp:
    def test_sse_extrai_ultimo_data(self):
        corpo = 'event: message\ndata: {"a":1}\n\nevent: message\ndata: {"id":2,"result":{}}\n'
        assert (
            json.loads(StreamableHTTPTransport._extract_json_from_sse(corpo))["id"] == 2
        )  # noqa: SLF001
        with pytest.raises(RuntimeError):
            StreamableHTTPTransport._extract_json_from_sse("sem dados")  # noqa: SLF001

    def test_url_nas_mensagens_nao_vaza_caminho(self):
        t = StreamableHTTPTransport("https://srv.exemplo.com:8443/segredo/token123?k=1")
        try:
            assert t._safe_url() == "https://srv.exemplo.com:8443"  # noqa: SLF001
        finally:
            t.close()

    def test_env_minimo(self, monkeypatch):
        monkeypatch.setenv("SEGREDO", "x")
        assert "SEGREDO" not in montar_env_minimo()
        assert montar_env_minimo({"A": 1})["A"] == "1"
