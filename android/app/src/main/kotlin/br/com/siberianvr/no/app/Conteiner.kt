package br.com.siberianvr.no.app

import android.content.Context
import br.com.siberianvr.no.nucleo.ClienteDoNo

/** Junta as peças do app (sem framework de injeção, para manter simples). */
class Conteiner(contexto: Context) {
    val armazenamento = ArmazenamentoSeguroAndroid(contexto.applicationContext)
    val configuracao = RepositorioDeConfiguracao(contexto.applicationContext)

    /** Cliente com a configuração atual, ou null se o app ainda não foi configurado. */
    fun criar_cliente(): ClienteDoNo? {
        val cfg = configuracao.configuracao_ou_nulo() ?: return null
        return try {
            ClienteDoNo(cfg, armazenamento)
        } catch (e: IllegalArgumentException) {
            null // certificado salvo inválido
        }
    }
}
