package br.com.siberianvr.no.nucleo

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement

/** Os modelos Kotlin precisam concordar com os arquivos de contrato/ (função). */
class ContratoTest {
    private val json = Json { ignoreUnknownKeys = true }
    private val estrito = Json { encodeDefaults = false }

    private fun arvore(texto: String): JsonElement = json.parseToJsonElement(texto)

    @Test
    fun pedido_completo_serializa_igual_ao_contrato() {
        val lido = json.decodeFromString<PedidoConversa>(ler_contrato("pedido_conversar.json"))
        assertEquals(arvore(ler_contrato("pedido_conversar.json")), arvore(estrito.encodeToString(lido)))
    }

    @Test
    fun pedido_minimo_nao_envia_conversa_id() {
        val pedido = PedidoConversa("Quem é você?")
        assertEquals(
            arvore(ler_contrato("pedido_conversar_minimo.json")),
            arvore(estrito.encodeToString(pedido)),
        )
    }

    @Test
    fun respostas_do_contrato_sao_lidas() {
        val c = json.decodeFromString<RespostaConversa>(ler_contrato("resposta_conversar.json"))
        assertEquals(RespostaConversa("Sou o Nó Único.", "abc-123", 1), c)
        assertEquals(
            RespostaSaude("ok", "1"),
            json.decodeFromString<RespostaSaude>(ler_contrato("resposta_saude.json")),
        )
        assertEquals(
            RespostaErro("nao_autorizado", "Token ausente ou inválido."),
            json.decodeFromString<RespostaErro>(ler_contrato("resposta_erro.json")),
        )
    }

    @Test
    fun esquema_openapi_declara_os_mesmos_campos() {
        val esquema = ler_contrato("openapi.json")
        for (campo in listOf("mensagem", "conversa_id", "resposta", "turnos", "versao_api", "erro")) {
            assert("\"$campo\"" in esquema) { "campo $campo sumiu do contrato" }
        }
    }
}
