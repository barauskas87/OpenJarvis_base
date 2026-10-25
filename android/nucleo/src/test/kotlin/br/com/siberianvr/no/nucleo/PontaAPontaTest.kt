package br.com.siberianvr.no.nucleo

import java.io.BufferedReader
import java.io.File
import java.io.InputStreamReader
import java.util.concurrent.TimeUnit
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.Assumptions.assumeTrue

/**
 * Cliente Kotlin contra o servidor Python REAL (TLS autoassinado de verdade).
 * Só roda quando NO_PYTHON aponta para um Python com as dependências instaladas.
 */
class PontaAPontaTest {
    private var processo: Process? = null
    private lateinit var config: ConfiguracaoDoNo
    private lateinit var token: String

    @BeforeTest
    fun subir_servidor() {
        val python = System.getProperty("no.python").orEmpty()
        assumeTrue(python.isNotBlank(), "NO_PYTHON não definido; teste ponta a ponta ignorado")
        val pecas = System.getProperty("no.pecas")
        val p = ProcessBuilder(python, "-I", File(pecas, "ferramentas/servidor_de_teste.py").path)
            .redirectErrorStream(false)
            .start()
        processo = p
        val linha = BufferedReader(InputStreamReader(p.inputStream)).readLine()
            ?: error("servidor de teste não respondeu: " + p.errorStream.bufferedReader().readText())
        val dados = Json.parseToJsonElement(linha).jsonObject
        token = dados["token"]!!.jsonPrimitive.content
        config = ConfiguracaoDoNo(
            "https://localhost:" + dados["porta"]!!.jsonPrimitive.content + "/",
            ConfiancaTls.CertificadoFixo(dados["certificado_pem"]!!.jsonPrimitive.content),
        )
    }

    @AfterTest
    fun derrubar_servidor() {
        processo?.let {
            it.outputStream.close() // fecha o stdin: o servidor encerra
            if (!it.waitFor(5, TimeUnit.SECONDS)) it.destroyForcibly()
        }
    }

    @Test
    fun saude_e_conversa_pelo_tls_real() {
        val cliente = ClienteDoNo(config, ArmazenamentoEmMemoria(token))
        assertEquals("ok", cliente.verificar_saude().status)
        val primeira = cliente.conversar("olá")
        assertEquals("eco:olá", primeira.resposta)
        assertEquals(1, primeira.turnos)
        val segunda = cliente.conversar("de novo", primeira.conversaId)
        assertEquals(2, segunda.turnos) // o servidor lembrou da conversa
        assertEquals(primeira.conversaId, segunda.conversaId)
    }

    @Test
    fun token_errado_e_recusado_pelo_servidor_real() {
        val cliente = ClienteDoNo(config, ArmazenamentoEmMemoria("nu_tokenQueNaoExiste"))
        assertFailsWith<ErroDoNo.NaoAutorizado> { cliente.conversar("oi") }
    }

    @Test
    fun segredo_na_resposta_chega_mascarado() {
        val cliente = ClienteDoNo(config, ArmazenamentoEmMemoria(token))
        val r = cliente.conversar("minha chave é AKIAABCDEFGHIJKLMNOP")
        assert("AKIAABCDEFGHIJKLMNOP" !in r.resposta) { r.resposta }
    }

    @Test
    fun unicode_ida_e_volta() {
        val cliente = ClienteDoNo(config, ArmazenamentoEmMemoria(token))
        assertEquals("eco:olá 🌎 日本語", cliente.conversar("olá 🌎 日本語").resposta)
    }

    @Test
    fun conversa_id_do_cliente_e_aceito_pelo_servidor() {
        val cliente = ClienteDoNo(config, ArmazenamentoEmMemoria(token))
        assertEquals("minha-conversa_1", cliente.conversar("oi", "minha-conversa_1").conversaId)
    }
}
