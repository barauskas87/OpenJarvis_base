package br.com.siberianvr.no.nucleo

import kotlinx.serialization.Serializable

/** Formato único de erro do servidor. */
@Serializable
data class RespostaErro(
    val erro: String,
    val mensagem: String,
)
