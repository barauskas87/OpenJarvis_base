"""Teste de mutação da API do Nó.

Injeta defeitos de segurança conhecidos, um por vez, numa CÓPIA da árvore, e
confere que a suíte os detecta. Sai com código 1 se algum defeito escapar.

Uso (a partir de ``pecas_no_unico/``):
    python ferramentas/mutacao_servidor.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TESTE = "Tests/test_servidor.py"

# (descrição, arquivo relativo a src/openjarvis, trecho original, trecho mutante)
MUTACOES = [
    ("auth aceita qualquer token", "servidor/autenticacao.py",
     "                achado = conhecido[:12]", "                achado = conhecido[:12]\n        achado = achado or 'x'"),
    ("auth sem comparação em tempo constante", "servidor/autenticacao.py",
     "if hmac.compare_digest(candidato, conhecido):", "if candidato == conhecido:"),
    ("auth aceita hash malformado", "servidor/autenticacao.py",
     "            if not _HEX64.match(texto):\n                raise ValueError(\"hash de token inválido (esperado SHA-256 em hex)\")\n", ""),
    ("auth aceita lista vazia", "servidor/autenticacao.py",
     "        if not validos:", "        if False:"),
    ("auth sem limite de tamanho de token", "servidor/autenticacao.py",
     " or len(token) > TAMANHO_MAX_TOKEN", ""),
    ("rota sem autenticação", "servidor/aplicacao.py",
     "        if dono is None:\n            origem", "        dono = dono or 'anonimo'\n        if False:\n            origem"),
    ("sem limite por token", "servidor/aplicacao.py",
     "        if not permitido:\n            return _erro(429, \"limite_de_uso\"", "        if False:\n            return _erro(429, \"limite_de_uso\""),
    ("sem limite de falhas", "servidor/aplicacao.py",
     "            if not permitido:\n                return _erro(429, \"muitas_tentativas\"", "            if False:\n                return _erro(429, \"muitas_tentativas\""),
    ("sem teto no cabeçalho de tamanho", "servidor/aplicacao.py",
     "if int(declarado) > tamanho_max_corpo:", "if False:"),
    ("sem teto na leitura em pedaços", "servidor/aplicacao.py",
     "            if len(bruto) > tamanho_max_corpo:", "            if False:"),
    ("resposta sem remoção de segredos", "servidor/aplicacao.py",
     "resposta = removedor.redact(resultado.resposta)", "resposta = resultado.resposta"),
    ("histórico sem separação por dono", "servidor/aplicacao.py",
     "anteriores = memoria.obter(dono, conversa_id)", "anteriores = memoria.obter('x', conversa_id)"),
    ("histórico gravado sob outro dono", "servidor/aplicacao.py",
     "memoria.registrar(dono, conversa_id,", "memoria.registrar('x', conversa_id,"),
    ("erro 500 vaza a exceção", "servidor/aplicacao.py",
     "            return _erro(500, \"falha_interna\", \"Erro interno.\")", "            return _erro(500, \"falha_interna\", str(__import__('sys').exc_info()[1]))"),
    ("422 ecoa a mensagem", "servidor/aplicacao.py",
     "422, \"pedido_invalido\", \"Campos inválidos: \" + \", \".join(campos) + \".\"", "422, \"pedido_invalido\", str(exc)"),
    ("vaga liberada antes do fim do trabalho", "servidor/aplicacao.py",
     "        await sem.acquire()", "        pass"),
    ("sem limite de simultâneas", "servidor/aplicacao.py",
     "        if sem.locked():", "        if False:"),
    ("sem tempo limite", "servidor/aplicacao.py",
     "await asyncio.wait_for(\n                run_in_threadpool(trabalho), tempo_limite_s\n            )", "await run_in_threadpool(trabalho)"),
    ("docs públicas ligadas", "servidor/aplicacao.py",
     "        docs_url=None,", "        docs_url='/docs',"),
    ("sem cabeçalho no-store", "servidor/aplicacao.py",
     "        resposta.headers[\"Cache-Control\"] = \"no-store\"\n", ""),
    ("sem WWW-Authenticate", "servidor/aplicacao.py",
     "                {\"WWW-Authenticate\": \"Bearer\"},", "                None,"),
    ("histórico vazio descartado", "servidor/aplicacao.py",
     "memoria = historico if historico is not None else HistoricoDeConversas()", "memoria = historico or HistoricoDeConversas()"),
    ("modelo aceita campo extra", "servidor/modelos.py",
     "model_config = ConfigDict(extra=\"forbid\")", "model_config = ConfigDict(extra=\"ignore\")"),
    ("mensagem só de espaço aceita", "servidor/modelos.py",
     "        if not valor.strip():\n            raise ValueError(\"mensagem vazia\")\n", ""),
    ("conversa_id sem padrão", "servidor/modelos.py",
     "Field(default=None, pattern=PADRAO_CONVERSA_ID)", "Field(default=None)"),
    ("histórico sem teto de pares", "servidor/historico.py",
     "pares[-self._max_pares :]", "pares"),
    ("histórico sem teto de conversas", "servidor/historico.py",
     "            while len(self._dados) > self._max_conversas:", "            while False:"),
    ("CLI aceita exposição sem TLS", "servidor/principal.py",
     "    if host in _LOCAIS or certificado or atras_de_proxy:", "    if True:"),
    ("CLI aceita certificado sem chave", "servidor/principal.py",
     "    if bool(certificado) != bool(chave):", "    if False:"),
    ("CLI imprime o token no lugar do hash", "servidor/principal.py",
     "hash_token(token))", "token)"),
]


def main() -> int:
    escaparam = []
    with tempfile.TemporaryDirectory() as tmp:
        for descricao, arquivo, original, mutante in MUTACOES:
            copia = Path(tmp) / "t"
            if copia.exists():
                shutil.rmtree(copia)
            shutil.copytree(
                RAIZ, copia,
                ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".ruff_cache"),
            )
            alvo = copia / "src" / "openjarvis" / arquivo
            texto = alvo.read_text(encoding="utf-8")
            if original not in texto:
                print(f"INVÁLIDA   {descricao} (trecho não encontrado)")
                escaparam.append(descricao)
                continue
            alvo.write_text(texto.replace(original, mutante, 1), encoding="utf-8")
            r = subprocess.run(
                [sys.executable, "-I", "-m", "pytest", "-q", "-x", "-p",
                 "no:cacheprovider", TESTE],
                cwd=copia, capture_output=True, text=True, timeout=600,
            )
            pegou = r.returncode != 0
            print(("PEGOU     " if pegou else "ESCAPOU   ") + descricao)
            if not pegou:
                escaparam.append(descricao)
    print(f"mutações: {len(MUTACOES)}  escaparam: {escaparam}")
    return 1 if escaparam else 0


if __name__ == "__main__":
    raise SystemExit(main())
