package br.com.siberianvr.no.nucleo

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.SocketPolicy

class ClienteEstabilidadeTest {
    private fun resposta(corpo: String, codigo: Int = 200) =
        MockResponse().setResponseCode(codigo).setBody(corpo)

    @Test
    fun respostas_fora_do_contrato_viram_RespostaInesperada() {
        val ruins = listOf(
            "<html>oi</html>", "", "null", "[]", "{}", "nao json",
            """{"resposta":"x"}""",
            """{"resposta":"x","conversa_id":"c","turnos":"um"}""",
            """{"resposta":1,"conversa_id":"c","turnos":1}""",
        )
        for (corpo in ruins) {
            NoDeMentira().use { no ->
                no.servidor.enqueue(resposta(corpo))
                assertFailsWith<ErroDoNo.RespostaInesperada>(corpo) { no.cliente().conversar("oi") }
            }
        }
    }

    @Test
    fun campos_novos_do_servidor_nao_quebram_o_app() {
        NoDeMentira().use { no ->
            no.servidor.enqueue(resposta("""{"resposta":"a","conversa_id":"c","turnos":2,"novo":{"x":[1,2]}}"""))
            assertEquals(2, no.cliente().conversar("oi").turnos)
        }
    }

    @Test
    fun resposta_grande_demais_e_recusada() {
        NoDeMentira().use { no ->
            // JSON válido: sem o teto de tamanho, esta resposta seria aceita.
            val grande = """{"resposta":"${"a".repeat(5000)}","conversa_id":"c","turnos":1}"""
            no.servidor.enqueue(resposta(grande))
            val cliente = no.cliente(config = no.config(tamanhoMax = 1000))
            assertFailsWith<ErroDoNo.RespostaInesperada> { cliente.conversar("oi") }
            // e o mesmo corpo é aceito quando o teto é maior
            no.servidor.enqueue(resposta(grande))
            assertEquals(5000, no.cliente(config = no.config(tamanhoMax = 10_000)).conversar("oi").resposta.length)
        }
    }

    @Test
    fun conexao_derrubada_vira_SemConexao() {
        NoDeMentira().use { no ->
            no.servidor.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AT_START))
            assertFailsWith<ErroDoNo.SemConexao> { no.cliente().conversar("oi") }
        }
    }

    @Test
    fun post_nao_e_repetido_sozinho_quando_a_conexao_reaproveitada_cai() {
        NoDeMentira().use { no ->
            val cliente = no.cliente()
            no.servidor.enqueue(resposta(RESPOSTA_OK))
            cliente.conversar("primeira") // deixa uma conexão viva no pool
            // O Nó recebe o segundo pedido e a conexão cai. Se o cliente repetisse sozinho,
            // a ação poderia ser executada duas vezes no Nó.
            no.servidor.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AFTER_REQUEST))
            no.servidor.enqueue(resposta(RESPOSTA_OK))
            assertFailsWith<ErroDoNo.SemConexao> { cliente.conversar("segunda") }
            assertEquals(2, no.servidor.requestCount) // 1ª + a que caiu; nenhuma repetição
        }
    }

    @Test
    fun servidor_parado_vira_SemConexao() {
        val no = NoDeMentira()
        val cliente = no.cliente()
        no.close()
        assertFailsWith<ErroDoNo.SemConexao> { cliente.conversar("oi") }
    }

    @Test
    fun leitura_lenta_vira_TempoEsgotado_sem_travar() {
        NoDeMentira().use { no ->
            no.servidor.enqueue(
                MockResponse().setBody(RESPOSTA_OK).setBodyDelay(5, java.util.concurrent.TimeUnit.SECONDS),
            )
            val inicio = System.nanoTime()
            assertFailsWith<ErroDoNo.TempoEsgotado> {
                no.cliente(config = no.config(tempoLeitura = 1)).conversar("oi")
            }
            assertTrue((System.nanoTime() - inicio) / 1e9 < 4, "demorou além do tempo de leitura")
        }
    }

    @Test
    fun retry_after_absurdo_usa_o_padrao() {
        for (valor in listOf("999999", "-5", "abc", "0", "")) {
            NoDeMentira().use { no ->
                no.servidor.enqueue(MockResponse().setResponseCode(429).addHeader("Retry-After", valor))
                val erro = assertFailsWith<ErroDoNo.LimiteExcedido>(valor) { no.cliente().conversar("oi") }
                assertEquals(1L, erro.segundos, valor)
            }
        }
    }

    @Test
    fun pedido_invalido_e_barrado_antes_de_sair() {
        NoDeMentira().use { no ->
            val c = no.cliente()
            assertFailsWith<ErroDoNo.PedidoInvalido> { c.conversar("") }
            assertFailsWith<ErroDoNo.PedidoInvalido> { c.conversar(" \n\t ") }
            assertFailsWith<ErroDoNo.PedidoInvalido> { c.conversar("a".repeat(8001)) }
            assertFailsWith<ErroDoNo.PedidoInvalido> { c.conversar("oi", "../x") }
            assertFailsWith<ErroDoNo.PedidoInvalido> { c.conversar("oi", "a".repeat(65)) }
            assertEquals(0, no.servidor.requestCount)
        }
    }

    @Test
    fun limite_de_mensagem_conta_caracteres_unicode_como_o_servidor() {
        NoDeMentira().use { no ->
            no.servidor.enqueue(resposta(RESPOSTA_OK))
            val emojis = "🌎".repeat(8000) // 16000 unidades UTF-16, 8000 caracteres
            no.cliente().conversar(emojis)
            assertEquals(1, no.servidor.requestCount)
            assertFailsWith<ErroDoNo.PedidoInvalido> { no.cliente().conversar("🌎".repeat(8001)) }
        }
    }

    @Test
    fun token_nunca_aparece_nas_mensagens_de_erro() {
        val token = "nu_SEGREDO_NAO_PODE_VAZAR_123"
        val cenarios: List<Pair<String, MockResponse?>> = listOf(
            "401" to MockResponse().setResponseCode(401),
            "429" to MockResponse().setResponseCode(429),
            "500" to MockResponse().setResponseCode(500).setBody(token),
            "lixo" to MockResponse().setBody(token),
            "queda" to MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AT_START),
        )
        for ((nome, resposta) in cenarios) {
            NoDeMentira().use { no ->
                no.servidor.enqueue(resposta!!)
                val erro = assertFailsWith<ErroDoNo>(nome) { no.cliente(token = token).conversar("oi") }
                assertFalse(token in (erro.message ?: ""), nome)
                assertFalse(token in (erro.cause?.message ?: ""), nome)
                assertFalse(token in erro.toString(), nome)
            }
        }
    }

    @Test
    fun token_com_formato_perigoso_e_recusado_sem_vazar() {
        NoDeMentira().use { no ->
            for (ruim in listOf("nu_a\nX-Injetado: 1", "nu_a\r\nb", "nu a", "nu_é", "a".repeat(300), "nu_\u0000")) {
                val erro = assertFailsWith<ErroDoNo.PedidoInvalido> { no.cliente(token = ruim).conversar("oi") }
                assertFalse(ruim in (erro.message ?: ""))
            }
            assertEquals(0, no.servidor.requestCount)
        }
    }
}
