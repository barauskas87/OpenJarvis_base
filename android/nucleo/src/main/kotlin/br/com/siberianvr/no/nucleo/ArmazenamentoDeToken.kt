package br.com.siberianvr.no.nucleo

/** Onde o token fica guardado. No Android, a implementação usa o Keystore. */
interface ArmazenamentoDeToken {
    fun ler_token(): String?

    fun gravar_token(token: String)

    fun apagar_token()
}
