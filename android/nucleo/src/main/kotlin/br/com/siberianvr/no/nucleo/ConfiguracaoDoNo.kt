package br.com.siberianvr.no.nucleo

import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/**
 * Endereço e regras de confiança do Nó.
 *
 * Só aceita https. A única exceção é http para localhost/127.0.0.1, e só se
 * [permitirHttpLocal] for ligado de propósito (desenvolvimento).
 */
class ConfiguracaoDoNo(
    urlBase: String,
    val confianca: ConfiancaTls = ConfiancaTls.Sistema(),
    val permitirHttpLocal: Boolean = false,
    val tempoConexaoSegundos: Long = 10,
    val tempoLeituraSegundos: Long = 130,
    val tamanhoMaxRespostaBytes: Long = 1_048_576,
) {
    val urlBase: HttpUrl

    init {
        val url = urlBase.toHttpUrlOrNull()
            ?: throw IllegalArgumentException("URL do Nó inválida.")
        val local = url.host == "localhost" || url.host == "127.0.0.1" || url.host == "::1"
        require(url.isHttps || (permitirHttpLocal && local)) {
            "O Nó só pode ser acessado por https."
        }
        require(url.username.isEmpty() && url.password.isEmpty()) {
            "A URL do Nó não pode conter usuário ou senha."
        }
        this.urlBase = url
    }
}
