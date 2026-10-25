package br.com.siberianvr.no.app

import android.content.Context
import br.com.siberianvr.no.nucleo.ConfiancaTls
import br.com.siberianvr.no.nucleo.ConfiguracaoDoNo

/** Endereço e certificado do Nó (não são segredos; o token fica em outro lugar). */
class RepositorioDeConfiguracao(contexto: Context) {
    private val preferencias = contexto.getSharedPreferences("no_config", Context.MODE_PRIVATE)

    fun url(): String = preferencias.getString("url", "") ?: ""

    fun certificado_pem(): String = preferencias.getString("certificado", "") ?: ""

    fun gravar(url: String, certificadoPem: String) {
        preferencias.edit().putString("url", url.trim()).putString("certificado", certificadoPem.trim()).apply()
    }

    /** Monta a configuração ou devolve null se ainda não houver (ou for inválida). */
    fun configuracao_ou_nulo(): ConfiguracaoDoNo? {
        val url = url()
        if (url.isBlank()) return null
        val pem = certificado_pem()
        val confianca = if (pem.isBlank()) ConfiancaTls.Sistema() else ConfiancaTls.CertificadoFixo(pem)
        return try {
            ConfiguracaoDoNo(url, confianca)
        } catch (e: IllegalArgumentException) {
            null
        }
    }
}
