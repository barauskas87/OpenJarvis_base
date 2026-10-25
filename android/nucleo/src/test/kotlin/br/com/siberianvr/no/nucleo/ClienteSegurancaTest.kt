package br.com.siberianvr.no.nucleo

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import okhttp3.CertificatePinner
import okhttp3.mockwebserver.MockResponse
import okhttp3.tls.HandshakeCertificates

/** Confiança TLS, pins e redirecionamentos (interferência entre hosts). */
class ClienteSegurancaTest {
    private fun ok() = MockResponse().setBody(RESPOSTA_OK)

    @Test
    fun certificado_fixo_correto_conecta() {
        NoDeMentira().use { no ->
            no.servidor.enqueue(ok())
            assertEquals("c1", no.cliente().conversar("oi").conversaId)
        }
    }

    @Test
    fun certificado_diferente_do_fixo_e_recusado() {
        NoDeMentira().use { no ->
            NoDeMentira().use { outro ->
                no.servidor.enqueue(ok())
                val cliente = no.cliente(config = no.config(ConfiancaTls.CertificadoFixo(outro.pem)))
                assertFailsWith<ErroDoNo.SemConexao> { cliente.conversar("oi") }
                assertEquals(0, no.servidor.requestCount)
            }
        }
    }

    @Test
    fun certificado_autoassinado_nao_e_aceito_pelo_modo_sistema() {
        NoDeMentira().use { no ->
            no.servidor.enqueue(ok())
            val cliente = no.cliente(config = no.config(ConfiancaTls.Sistema()))
            assertFailsWith<ErroDoNo.SemConexao> { cliente.conversar("oi") }
        }
    }

    @Test
    fun certificado_para_outro_nome_e_recusado() {
        NoDeMentira(hostSan = "outro-host.exemplo").use { no ->
            no.servidor.enqueue(ok())
            assertFailsWith<ErroDoNo.SemConexao> { no.cliente().conversar("oi") }
        }
    }

    // Os dois testes abaixo confiam numa CA de teste (como se fosse do sistema)
    // e verificam que o PIN continua mandando.

    private fun cliente_com_ca_de_teste(no: NoDeMentira, pins: List<String>): ClienteDoNo {
        val confia = HandshakeCertificates.Builder().addTrustedCertificate(no.certificado.certificate).build()
        return ClienteDoNo(
            no.config(ConfiancaTls.Sistema(pins)),
            ArmazenamentoEmMemoria(TOKEN_DE_TESTE),
        ) { it.sslSocketFactory(confia.sslSocketFactory(), confia.trustManager) }
    }

    @Test
    fun pin_correto_conecta() {
        NoDeMentira().use { no ->
            no.servidor.enqueue(ok())
            val pin = CertificatePinner.pin(no.certificado.certificate)
            assertEquals("c1", cliente_com_ca_de_teste(no, listOf(pin)).conversar("oi").conversaId)
        }
    }

    @Test
    fun pin_errado_e_recusado_mesmo_com_certificado_confiavel() {
        NoDeMentira().use { no ->
            NoDeMentira().use { outro ->
                no.servidor.enqueue(ok())
                val pinErrado = CertificatePinner.pin(outro.certificado.certificate)
                val cliente = cliente_com_ca_de_teste(no, listOf(pinErrado))
                assertFailsWith<ErroDoNo.SemConexao> { cliente.conversar("oi") }
                assertEquals(0, no.servidor.requestCount)
            }
        }
    }

    @Test
    fun redirecionamento_nao_e_seguido_e_o_token_nao_vai_para_outro_host() {
        NoDeMentira().use { no ->
            NoDeMentira().use { destino ->
                no.servidor.enqueue(
                    MockResponse().setResponseCode(302).addHeader("Location", destino.url + "v1/conversar"),
                )
                destino.servidor.enqueue(ok())
                val erro = assertFailsWith<ErroDoNo.ErroDoServidor> { no.cliente().conversar("oi") }
                assertEquals(302, erro.codigoHttp)
                assertEquals(0, destino.servidor.requestCount)
            }
        }
    }

    @Test
    fun redirecionamento_de_https_para_http_tambem_nao_e_seguido() {
        NoDeMentira().use { no ->
            no.servidor.enqueue(
                MockResponse().setResponseCode(307).addHeader("Location", "http://localhost:1/"),
            )
            assertFailsWith<ErroDoNo.ErroDoServidor> { no.cliente().conversar("oi") }
        }
    }
}
