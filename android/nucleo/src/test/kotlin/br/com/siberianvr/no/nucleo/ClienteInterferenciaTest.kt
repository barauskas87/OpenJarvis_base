package br.com.siberianvr.no.nucleo

import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.RecordedRequest

class ClienteInterferenciaTest {
    /** Responde com a própria mensagem e o final do token recebido. */
    private val eco = object : Dispatcher() {
        override fun dispatch(request: RecordedRequest): MockResponse {
            val mensagem = Json.parseToJsonElement(request.body.readUtf8())
                .jsonObject["mensagem"]!!.jsonPrimitive.content
            val finalDoToken = request.getHeader("Authorization")!!.takeLast(4)
            return MockResponse().setBody(
                """{"resposta":"$mensagem","conversa_id":"$finalDoToken","turnos":1}""",
            )
        }
    }

    @Test
    fun threads_simultaneas_recebem_a_propria_resposta() {
        NoDeMentira().use { no ->
            no.servidor.dispatcher = eco
            val cliente = no.cliente()
            val pool = Executors.newFixedThreadPool(16)
            val erros = java.util.concurrent.ConcurrentLinkedQueue<String>()
            val fim = CountDownLatch(16)
            repeat(16) { i ->
                pool.submit {
                    try {
                        repeat(10) { j ->
                            val msg = "t$i-$j"
                            val r = cliente.conversar(msg)
                            if (r.resposta != msg) erros.add("$msg -> ${r.resposta}")
                        }
                    } catch (e: Throwable) {
                        erros.add(e.toString())
                    } finally {
                        fim.countDown()
                    }
                }
            }
            assertTrue(fim.await(60, TimeUnit.SECONDS))
            pool.shutdown()
            assertEquals(emptyList(), erros.toList())
        }
    }

    @Test
    fun dois_clientes_com_tokens_diferentes_nao_se_misturam() {
        NoDeMentira().use { no ->
            no.servidor.dispatcher = eco
            val a = no.cliente(token = "nu_tokenAAAA")
            val b = no.cliente(token = "nu_tokenBBBB")
            repeat(20) {
                assertEquals("AAAA", a.conversar("x").conversaId)
                assertEquals("BBBB", b.conversar("x").conversaId)
            }
        }
    }

    @Test
    fun trocar_o_token_em_uso_vale_no_pedido_seguinte() {
        NoDeMentira().use { no ->
            no.servidor.dispatcher = eco
            val memoria = ArmazenamentoEmMemoria("nu_tokenAAAA")
            val c = ClienteDoNo(no.config(), memoria)
            assertEquals("AAAA", c.conversar("x").conversaId)
            memoria.gravar_token("nu_tokenCCCC")
            assertEquals("CCCC", c.conversar("x").conversaId)
        }
    }
}
