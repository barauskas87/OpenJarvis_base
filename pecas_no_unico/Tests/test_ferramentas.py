"""file_read (N19), shell_exec (C3) e http_request (C1, C2)."""

from __future__ import annotations

import os
import sys
import time

import httpx
import pytest

from openjarvis.tools._paths import resolve_allowed_dirs
from openjarvis.tools.file_read import FileReadTool
from openjarvis.tools.http_request import HttpRequestTool
from openjarvis.tools.shell_exec import ShellExecTool

POSIX = os.name != "nt"


# --------------------------------------------------------------------------
# file_read
# --------------------------------------------------------------------------
@pytest.mark.funcao
class TestFileRead:
    def test_allowed_dirs_e_obrigatorio(self):
        for invalido in (None, [], ["  "], [3]):
            with pytest.raises(ValueError):
                FileReadTool(allowed_dirs=invalido)  # type: ignore[arg-type]

    def test_le_dentro_da_area(self, area):
        (area / "a.txt").write_bytes("olá\nmundo\n".encode("utf-8"))
        r = FileReadTool([str(area)]).execute(path=str(area / "a.txt"))
        assert r.success and r.content == "olá\nmundo\n"

    def test_caminho_relativo_fica_dentro_da_area(self, area):
        (area / "r.txt").write_text("x")
        assert FileReadTool([str(area)]).execute(path="r.txt").content == "x"

    def test_max_lines(self, area):
        (area / "l.txt").write_bytes(b"1\n2\n3\n")
        r = FileReadTool([str(area)]).execute(path="l.txt", max_lines=2)
        assert r.content == "1\n2\n"

    def test_fora_da_area_negado(self, area, tmp_path):
        fora = tmp_path / "fora.txt"
        fora.write_text("segredo")
        r = FileReadTool([str(area)]).execute(path=str(fora))
        assert not r.success and "outside allowed" in r.content

    def test_traversal_negado(self, area, tmp_path):
        (tmp_path / "fora.txt").write_text("x")
        r = FileReadTool([str(area)]).execute(path=str(area / ".." / "fora.txt"))
        assert not r.success

    @pytest.mark.skipif(not POSIX, reason="symlink")
    def test_symlink_para_fora_negado(self, area, tmp_path):
        fora = tmp_path / "fora.txt"
        fora.write_text("x")
        (area / "atalho.txt").symlink_to(fora)
        assert not FileReadTool([str(area)]).execute(path="atalho.txt").success

    def test_sensivel_negado_mesmo_dentro(self, area):
        for nome in (".env", ".ENV", "id_rsa", ".vault_key"):
            (area / nome).write_text("x")
            r = FileReadTool([str(area)]).execute(path=nome)
            assert not r.success and "sensitive" in r.content

    def test_sem_oraculo_de_existencia_fora_da_area(self, area, tmp_path):
        existe = tmp_path / "existe.txt"
        existe.write_text("x")
        t = FileReadTool([str(area)])
        a = t.execute(path=str(existe)).content
        b = t.execute(path=str(tmp_path / "nao_existe.txt")).content
        assert a.split(":")[0] == b.split(":")[0]  # ambos "Access denied"

    def test_arquivo_grande_negado(self, area):
        (area / "g.bin").write_bytes(b"a" * (1_048_576 + 10))
        r = FileReadTool([str(area)]).execute(path="g.bin")
        assert not r.success and "too large" in r.content

    def test_diretorio_e_inexistente(self, area):
        (area / "pasta").mkdir()
        t = FileReadTool([str(area)])
        assert "Not a file" in t.execute(path="pasta").content
        assert "not found" in t.execute(path="nada.txt").content

    def test_resolve_allowed_dirs_none_e_erro(self):
        with pytest.raises(ValueError):
            resolve_allowed_dirs(None)


@pytest.mark.estabilidade
class TestFileReadEstabilidade:
    def test_binario_vira_texto_com_substituicao(self, area):
        (area / "b.bin").write_bytes(b"\xff\xfe\x00abc")
        assert FileReadTool([str(area)]).execute(path="b.bin").success

    def test_parametros_estranhos(self, area):
        t = FileReadTool([str(area)])
        for p in (None, "", 5, ["x"], {"a": 1}):
            assert not t.execute(path=p).success
        assert not t.execute().success


# --------------------------------------------------------------------------
# shell_exec
# --------------------------------------------------------------------------
@pytest.mark.skipif(not POSIX, reason="comandos de shell POSIX")
@pytest.mark.funcao
class TestShellExec:
    def test_executa_e_devolve_saida(self):
        r = ShellExecTool().execute(command="echo oi")
        assert r.success and "oi" in r.content and r.metadata["returncode"] == 0

    def test_retorno_diferente_de_zero_e_falha(self):
        r = ShellExecTool().execute(command="exit 3")
        assert not r.success and r.metadata["returncode"] == 3

    def test_ambiente_minimo_nao_vaza_chaves(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "valor-secreto-xyz")
        r = ShellExecTool().execute(command="printenv")
        assert "valor-secreto-xyz" not in r.content
        assert "OPENAI_API_KEY" not in r.content

    def test_env_so_passa_o_que_o_construtor_permite(self, monkeypatch):
        monkeypatch.setenv("MINHA_VAR", "ok123")
        monkeypatch.setenv("OUTRA", "nao")
        r = ShellExecTool(env_permitido=["MINHA_VAR"]).execute(command="printenv")
        assert "ok123" in r.content and "nao" not in r.content

    def test_modelo_nao_consegue_pedir_passagem_de_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "valor-secreto-xyz")
        r = ShellExecTool().execute(
            command="printenv", env_passthrough=["OPENAI_API_KEY"]
        )
        assert "valor-secreto-xyz" not in r.content

    def test_timeout_mata_a_arvore_de_processos(self, tmp_path):
        pidfile = tmp_path / "pid"
        cmd = f"sleep 60 & echo $! > {pidfile}; wait"
        t0 = time.time()
        r = ShellExecTool().execute(command=cmd, timeout=1)
        assert not r.success and "timed out" in r.content
        assert time.time() - t0 < 10
        pid = int(pidfile.read_text())
        for _ in range(30):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            pytest.fail("processo-neto sobreviveu ao timeout")

    def test_saida_truncada(self):
        r = ShellExecTool().execute(
            command=f"{sys.executable} -c \"print('a'*300000)\""
        )
        assert "truncated" in r.content
        assert len(r.content) < 120_000

    def test_working_dir_invalido(self, tmp_path):
        t = ShellExecTool()
        assert not t.execute(command="pwd", working_dir=str(tmp_path / "x")).success
        arq = tmp_path / "f"
        arq.write_text("x")
        assert not t.execute(command="pwd", working_dir=str(arq)).success

    def test_working_dir_confinado(self, area, tmp_path):
        t = ShellExecTool(allowed_dirs=[str(area)])
        assert t.execute(command="pwd", working_dir=str(area)).success
        r = t.execute(command="pwd", working_dir=str(tmp_path))
        assert not r.success and "outside" in r.content

    def test_spec_exige_confirmacao_e_timeout_do_executor_maior(self):
        spec = ShellExecTool().spec
        assert spec.requires_confirmation
        assert spec.timeout_seconds > 300  # executor não desiste antes da ferramenta
        assert "env_passthrough" not in spec.parameters["properties"]


@pytest.mark.estabilidade
class TestShellExecEstabilidade:
    def test_entradas_invalidas(self):
        t = ShellExecTool()
        for cmd in (None, "", 5, ["ls"]):
            assert not t.execute(command=cmd).success

    @pytest.mark.parametrize("valor", ["abc", None, -5, 10**9, 0])
    def test_timeout_invalido_e_limitado(self, valor):
        r = ShellExecTool().execute(command="true", timeout=valor)
        assert r.success
        assert 1 <= r.metadata["timeout_used"] <= 300


# --------------------------------------------------------------------------
# http_request
# --------------------------------------------------------------------------
def _cliente(gerente):
    """Cria a ferramenta com transporte falso; ``gerente(request)`` -> Response."""
    return HttpRequestTool(transporte=httpx.MockTransport(gerente))


PUBLICO = "https://93.184.216.34"


@pytest.mark.funcao
class TestHttpRequest:
    def test_get_simples(self):
        t = _cliente(lambda req: httpx.Response(200, text="olá", headers={"x": "1"}))
        r = t.execute(url=f"{PUBLICO}/a")
        assert r.success and r.content == "olá" and r.metadata["status_code"] == 200

    def test_c1_cabecalho_nao_expande_variavel_de_ambiente(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-super-secreta-123456789012345")
        vistos = {}

        def h(req):
            vistos.update(req.headers)
            return httpx.Response(200, text="ok")

        r = _cliente(h).execute(
            url=f"{PUBLICO}/x", headers={"Authorization": "Bearer $OPENAI_API_KEY"}
        )
        assert r.success
        assert vistos["authorization"] == "Bearer $OPENAI_API_KEY"
        assert "sk-super-secreta" not in str(vistos)

    def test_c2_redirecionamento_para_ip_privado_bloqueado(self):
        consultados = []

        def h(req):
            consultados.append(req.url.host)
            if req.url.host == "10.0.0.5":
                return httpx.Response(200, text="SEGREDO-INTERNO")
            return httpx.Response(302, headers={"location": "http://10.0.0.5/admin"})

        r = _cliente(h).execute(url=f"{PUBLICO}/x")
        assert not r.success and "blocked redirect" in r.content
        assert "SEGREDO-INTERNO" not in r.content
        assert "10.0.0.5" not in consultados  # a requisição interna nem saiu

    def test_c2_redirecionamento_para_metadata_bloqueado(self):
        consultados = []

        def h(req):
            consultados.append(req.url.host)
            if req.url.host == "169.254.169.254":
                return httpx.Response(200, text="CREDENCIAIS-DA-NUVEM")
            return httpx.Response(
                301, headers={"location": "http://169.254.169.254/latest"}
            )

        r = _cliente(h).execute(url=f"{PUBLICO}/x")
        assert not r.success and "CREDENCIAIS" not in r.content
        assert "169.254.169.254" not in consultados

    def test_redirecionamento_publico_e_seguido(self):
        def h(req):
            if req.url.path == "/a":
                return httpx.Response(302, headers={"location": "/b"})
            return httpx.Response(200, text="chegou")

        r = _cliente(h).execute(url=f"{PUBLICO}/a")
        assert r.success and r.content == "chegou"

    def test_authorization_nao_vai_para_outro_host(self):
        vistos = []

        def h(req):
            vistos.append((req.url.host, req.headers.get("authorization")))
            if req.url.host == "93.184.216.34":
                return httpx.Response(302, headers={"location": "https://8.8.8.8/z"})
            return httpx.Response(200, text="ok")

        _cliente(h).execute(url=f"{PUBLICO}/a", headers={"Authorization": "Bearer abc"})
        assert vistos[0] == ("93.184.216.34", "Bearer abc")
        assert vistos[1] == ("8.8.8.8", None)

    def test_ssrf_na_url_inicial(self):
        r = _cliente(lambda req: httpx.Response(200)).execute(url="http://127.0.0.1/")
        assert not r.success and "SSRF" in r.content

    def test_resposta_truncada_em_1mb_sem_baixar_tudo(self):
        def h(req):
            return httpx.Response(200, content=b"a" * 3_000_000)

        r = _cliente(h).execute(url=f"{PUBLICO}/grande")
        assert r.success and r.metadata["truncated"]
        assert len(r.content) < 1_100_000

    @pytest.mark.parametrize(
        "nome", ["Host", "Connection", "Content-Length", "Transfer-Encoding"]
    )
    def test_cabecalhos_proibidos(self, nome):
        r = _cliente(lambda req: httpx.Response(200)).execute(
            url=f"{PUBLICO}/", headers={nome: "x"}
        )
        assert not r.success and "not allowed" in r.content

    def test_injecao_de_cabecalho_por_quebra_de_linha(self):
        r = _cliente(lambda req: httpx.Response(200)).execute(
            url=f"{PUBLICO}/", headers={"X-A": "ok\r\nX-Evil: 1"}
        )
        assert not r.success

    def test_metodo_nao_permitido(self):
        r = _cliente(lambda req: httpx.Response(200)).execute(
            url=f"{PUBLICO}/", method="TRACE"
        )
        assert not r.success


@pytest.mark.estabilidade
class TestHttpRequestEstabilidade:
    def test_cadeia_de_redirecionamentos_infinita(self):
        def h(req):
            return httpx.Response(302, headers={"location": f"{PUBLICO}/volta"})

        r = _cliente(h).execute(url=f"{PUBLICO}/a")
        assert not r.success and "redirects" in r.content

    def test_timeout_vira_resultado(self):
        def h(req):
            raise httpx.ReadTimeout("lento", request=req)

        r = _cliente(h).execute(url=f"{PUBLICO}/a")
        assert not r.success and "timed out" in r.content

    def test_erro_de_rede_nao_vaza_detalhe_interno(self):
        def h(req):
            raise httpx.ConnectError("falhou", request=req)

        r = _cliente(h).execute(url=f"{PUBLICO}/a")
        assert not r.success and "ConnectError" in r.content

    def test_parametros_invalidos(self):
        t = _cliente(lambda req: httpx.Response(200))
        for p in (
            {},
            {"url": None},
            {"url": 5},
            {"url": f"{PUBLICO}/", "headers": "x"},
        ):
            assert not t.execute(**p).success

    def test_timeout_limitado(self):
        # não deve levantar com valores absurdos
        t = _cliente(lambda req: httpx.Response(200, text="x"))
        assert t.execute(url=f"{PUBLICO}/", timeout="abc").success
        assert t.execute(url=f"{PUBLICO}/", timeout=10**9).success
