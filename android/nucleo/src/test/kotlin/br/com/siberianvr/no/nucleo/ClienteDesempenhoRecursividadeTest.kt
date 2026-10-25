package br.com.siberianvr.no.nucleo

import kotlin.test.Test
import kotlin.test.assertTrue
import okhttp3.mockwebserver.MockResponse

class ClienteDesempenhoRecursividadeTest {
    @Test
    fun duzentas_chamadas_seguidas_em_poucos_segundos() {
        NoDeMentira().use { no ->
            repeat(200) { no.servidor.enqueue(MockResponse().setBody(RESPOSTA_OK)) }
            val c = no.cliente()
            val inicio = System.nanoTime()
            repeat(200) { c.conversar("m$it") }
            val segundos = (System.nanoTime() - inicio) / 1e9
            assertTrue(segundos < 30, "200 chamadas levaram $segundos s")
        }
    }

    @Test
    fun json_muito_aninhado_na_resposta_nao_derruba_o_app() {
        val fundo = 100_000
        val corpo = """{"resposta":"a","conversa_id":"c","turnos":1,"x":""" +
            "[".repeat(fundo) + "]".repeat(fundo) + "}"
        NoDeMentira().use { no ->
            no.servidor.enqueue(MockResponse().setBody(corpo))
            try {
                no.cliente().conversar("oi")
            } catch (e: ErroDoNo) {
                // recusar também é aceitável; o que não pode é estourar a pilha
            }
        }
    }

    @Test
    fun resposta_com_texto_enorme_dentro_do_teto_e_lida() {
        NoDeMentira().use { no ->
            val texto = "a".repeat(900_000)
            no.servidor.enqueue(MockResponse().setBody("""{"resposta":"$texto","conversa_id":"c","turnos":1}"""))
            assertTrue(no.cliente().conversar("oi").resposta.length == 900_000)
        }
    }
}
