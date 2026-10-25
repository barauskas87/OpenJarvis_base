"""Teste de mutação do cliente Kotlin (núcleo do app Android).

Injeta defeitos de segurança, um por vez, numa CÓPIA do projeto e confere que
os testes do Gradle os detectam. Sai com código 1 se algum escapar.

Uso (a partir de ``pecas_no_unico/``; precisa de JDK 17+ e Gradle):
    python ferramentas/mutacao_cliente.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
ARQ = "android/nucleo/src/main/kotlin/br/com/siberianvr/no/nucleo/"

MUTACOES = [
    ("segue redirecionamentos", ARQ + "ClienteDoNo.kt",
     ".followRedirects(false)", ".followRedirects(true)"),
    ("segue redirecionamento https->http", ARQ + "ClienteDoNo.kt",
     ".followRedirects(false)\n            .followSslRedirects(false)",
     ".followRedirects(true)\n            .followSslRedirects(true)"),
    ("aceita http em qualquer host", ARQ + "ConfiguracaoDoNo.kt",
     "require(url.isHttps || (permitirHttpLocal && local))", "require(true)"),
    ("aceita usuário:senha na URL", ARQ + "ConfiguracaoDoNo.kt",
     "require(url.username.isEmpty() && url.password.isEmpty())", "require(true)"),
    ("não valida formato do token", ARQ + "ClienteDoNo.kt",
     "if (!PADRAO_TOKEN.matches(token))", "if (false)"),
    ("token vaza na mensagem de erro", ARQ + "ClienteDoNo.kt",
     'ErroDoNo.PedidoInvalido("Token com formato inválido.")', 'ErroDoNo.PedidoInvalido("Token inválido: $token")'),
    ("sem teto no tamanho da resposta", ARQ + "ClienteDoNo.kt",
     "if (fonte.buffer.size > config.tamanhoMaxRespostaBytes)", "if (false)"),
    ("pins ignorados", ARQ + "ClienteDoNo.kt",
     "construtor.certificatePinner(pinos.build())", ""),
    ("hostname não verificado", ARQ + "ClienteDoNo.kt",
     "        ajuste?.invoke(construtor)", "        construtor.hostnameVerifier { _, _ -> true }\n        ajuste?.invoke(construtor)"),
    ("certificado fixo vira confiança do sistema", ARQ + "ClienteDoNo.kt",
     ".addTrustedCertificate(ler_certificado(confianca.pem))", ".addPlatformTrustedCertificates()"),
    ("401 vira erro genérico", ARQ + "ClienteDoNo.kt",
     "401 -> throw ErroDoNo.NaoAutorizado()", "401 -> throw ErroDoNo.ErroDoServidor(401)"),
    ("limite de mensagem em unidades UTF-16", ARQ + "ClienteDoNo.kt",
     "mensagem.codePointCount(0, mensagem.length) > TAMANHO_MAX_MENSAGEM", "mensagem.length > TAMANHO_MAX_MENSAGEM"),
    ("saúde envia o token", ARQ + "ClienteDoNo.kt",
     'Request.Builder().url(url("v1/saude")).get().build()',
     'Request.Builder().url(url("v1/saude")).header("Authorization", "Bearer ${armazenamento.ler_token()}").get().build()'),
    ("campo novo do servidor quebra o app", ARQ + "ClienteDoNo.kt",
     "ignoreUnknownKeys = true", "ignoreUnknownKeys = false"),
    ("Retry-After absurdo aceito", ARQ + "ClienteDoNo.kt",
     "takeIf { it in 1..3600 }", "takeIf { true }"),
    ("reenvia POST automaticamente", ARQ + "ClienteDoNo.kt",
     ".retryOnConnectionFailure(false)", ".retryOnConnectionFailure(true)"),
]


def main() -> int:
    # Filtro opcional: ``python mutacao_cliente.py redirecion`` roda só as que casam.
    filtro = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    mutacoes = [m for m in MUTACOES if filtro in m[0].lower()]
    escaparam = []
    with tempfile.TemporaryDirectory() as tmp:
        for descricao, arquivo, original, mutante in mutacoes:
            copia = Path(tmp) / "t"
            if copia.exists():
                shutil.rmtree(copia)
            shutil.copytree(
                RAIZ, copia,
                ignore=shutil.ignore_patterns(
                    ".git", ".gradle", "build", "__pycache__", ".pytest_cache", ".anchor"
                ),
            )
            alvo = copia / arquivo
            texto = alvo.read_text(encoding="utf-8")
            if original not in texto:
                print(f"INVÁLIDA   {descricao} (trecho não encontrado)")
                escaparam.append(descricao)
                continue
            alvo.write_text(texto.replace(original, mutante, 1), encoding="utf-8")
            r = subprocess.run(
                ["gradle", "--no-daemon", "--offline", "-q", ":nucleo:test"],
                cwd=copia / "android", capture_output=True, text=True, timeout=900,
            )
            if "error:" in r.stdout.lower() + r.stderr.lower() and "e: file:" in r.stderr:
                print(f"INVÁLIDA   {descricao} (não compila)")
                escaparam.append(descricao)
                continue
            pegou = r.returncode != 0
            print(("PEGOU     " if pegou else "ESCAPOU   ") + descricao, flush=True)
            if not pegou:
                escaparam.append(descricao)
    print(f"mutações: {len(mutacoes)}  escaparam: {escaparam}")
    return 1 if escaparam else 0


if __name__ == "__main__":
    sys.exit(main())
