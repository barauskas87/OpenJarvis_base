package br.com.siberianvr.no.nucleo

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** Resposta de GET /v1/saude. */
@Serializable
data class RespostaSaude(
    val status: String,
    @SerialName("versao_api") val versaoApi: String,
)
