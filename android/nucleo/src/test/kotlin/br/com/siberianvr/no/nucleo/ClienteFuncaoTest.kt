package br.com.siberianvr.no.nucleo

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue
import okhttp3.mockwebserver.MockResponse

class ClienteFuncaoTest {
    private fun ok(corpo: String = RESPOSTA_OK) =
        MockResponse().setResponseCode(200).setBody(corpo).addHeader("Content-Type", "application/json")

    @Test
    fun saude_nao_envia_token() {
        NoDeMentira().use { no ->
            no.servidor.enqueue(ok("""{"status":"ok","versao_api":"1"}"""))
            val saude = no.cliente().verificar_saude()
            assertEquals(RespostaSaude("ok", "1"), saude)
            val pedido = no.servidor.takeRequest()
            assertEquals("/v1/saude", pedido.path)
            assertNull(pedido.getHeader("Authorization"))
        }
    }

    @Test
    fun conversar_envia_token_e_json_corretos() {
        NoDeMentira().use { no ->
            no.servidor.enqueue(ok())
            val r = no.cliente().conversar("Olá, Nó!", "abc-123")
            assertEquals(RespostaConversa("ok", "c1", 1), r)
            val pedido = no.servidor.takeRequest()
            assertEquals("POST", pedido.method)
            assertEquals("/v1/conversar", pedido.path)
            assertEquals("Bearer $TOKEN_DE_TESTE", pedido.getHeader("Authorization"))
            assertTrue(pedido.getHeader("Content-Type")!!.startsWith("application/json"))
            assertEquals("""{"mensagem":"Olá, Nó!","conversa_id":"abc-123"}""", pedido.body.readUtf8())
        }
    }

    @Test
    fun conversar_sem_conversa_id_omite_o_campo() {
        NoDeMentira().use { no ->
            no.servidor.enqueue(ok())
            no.cliente().conversar("oi")
            assertEquals("""{"mensagem":"oi"}""", no.servidor.takeRequest().body.readUtf8())
        }
    }

    @Test
    fun codigos_http_viram_erros_tipados() {
        val casos = listOf<Pair<MockResponse, (ErroDoNo) -> Boolean>>(
            MockResponse().setResponseCode(401) to { it is ErroDoNo.NaoAutorizado },
            MockResponse().setResponseCode(413) to { it is ErroDoNo.CorpoGrande },
            MockResponse().setResponseCode(504) to { it is ErroDoNo.TempoEsgotado },
            MockResponse().setResponseCode(500) to { it is ErroDoNo.ErroDoServidor && it.codigoHttp == 500 },
            MockResponse().setResponseCode(502).setBody("<html>Bad Gateway</html>") to
                { it is ErroDoNo.ErroDoServidor && it.codigoHttp == 502 },
            MockResponse().setResponseCode(429).addHeader("Retry-After", "7") to
                { it is ErroDoNo.LimiteExcedido && it.segundos == 7L },
            MockResponse().setResponseCode(503).addHeader("Retry-After", "3") to
                { it is ErroDoNo.NoOcupado && it.segundos == 3L },
            MockResponse().setResponseCode(400) to { it is ErroDoNo.PedidoInvalido },
            MockResponse().setResponseCode(422).setBody("""{"erro":"pedido_invalido","mensagem":"Campos inválidos: mensagem."}""") to
                { it is ErroDoNo.PedidoInvalido && "mensagem" in it.message!! },
        )
        for ((resposta, confere) in casos) {
            NoDeMentira().use { no ->
                no.servidor.enqueue(resposta)
                val erro = assertFailsWith<ErroDoNo>("HTTP ${resposta.status}") { no.cliente().conversar("oi") }
                assertTrue(confere(erro), "HTTP ${resposta.status}: $erro")
            }
        }
    }

    @Test
    fun sem_token_nao_chega_a_rede() {
        NoDeMentira().use { no ->
            assertFailsWith<ErroDoNo.SemToken> { no.cliente(token = null).conversar("oi") }
            assertFailsWith<ErroDoNo.SemToken> { no.cliente(token = "  ").conversar("oi") }
            assertEquals(0, no.servidor.requestCount)
        }
    }

    @Test
    fun apagar_token_impede_novos_pedidos() {
        NoDeMentira().use { no ->
            val memoria = ArmazenamentoEmMemoria(TOKEN_DE_TESTE)
            val cliente = ClienteDoNo(no.config(), memoria)
            no.servidor.enqueue(ok())
            cliente.conversar("oi")
            memoria.apagar_token()
            assertFailsWith<ErroDoNo.SemToken> { cliente.conversar("oi") }
        }
    }

    @Test
    fun saude_com_status_estranho_e_recusada() {
        NoDeMentira().use { no ->
            no.servidor.enqueue(ok("""{"status":"quebrado","versao_api":"1"}"""))
            assertFailsWith<ErroDoNo.RespostaInesperada> { no.cliente().verificar_saude() }
        }
    }
}
