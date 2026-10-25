package br.com.siberianvr.no.nucleo

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class ConfiguracaoTest {
    @Test
    fun aceita_https() {
        assertEquals("meu-no.exemplo", ConfiguracaoDoNo("https://meu-no.exemplo:8443/").urlBase.host)
    }

    @Test
    fun recusa_http_comum() {
        for (url in listOf("http://meu-no.exemplo", "http://192.168.0.5:8000", "http://localhost:8000")) {
            assertFailsWith<IllegalArgumentException>(url) { ConfiguracaoDoNo(url) }
        }
    }

    @Test
    fun http_local_so_com_a_chave_ligada() {
        ConfiguracaoDoNo("http://localhost:8000", permitirHttpLocal = true)
        ConfiguracaoDoNo("http://127.0.0.1:8000", permitirHttpLocal = true)
        assertFailsWith<IllegalArgumentException> {
            ConfiguracaoDoNo("http://meu-no.exemplo", permitirHttpLocal = true)
        }
    }

    @Test
    fun recusa_url_invalida_e_esquemas_estranhos() {
        for (url in listOf("", "nao é url", "ftp://x", "file:///etc/passwd", "javascript:alert(1)")) {
            assertFailsWith<IllegalArgumentException>(url) { ConfiguracaoDoNo(url) }
        }
    }

    @Test
    fun recusa_usuario_e_senha_na_url() {
        assertFailsWith<IllegalArgumentException> { ConfiguracaoDoNo("https://usuario:senha@no.exemplo") }
    }

    @Test
    fun certificado_pem_invalido_e_recusado() {
        val cfg = ConfiguracaoDoNo("https://no.exemplo", ConfiancaTls.CertificadoFixo("isto não é PEM"))
        assertFailsWith<IllegalArgumentException> { ClienteDoNo(cfg, ArmazenamentoEmMemoria("t")) }
    }
}
