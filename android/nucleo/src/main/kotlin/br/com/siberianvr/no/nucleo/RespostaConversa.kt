package br.com.siberianvr.no.nucleo

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** Resposta de POST /v1/conversar. */
@Serializable
data class RespostaConversa(
    val resposta: String,
    @SerialName("conversa_id") val conversaId: String,
    val turnos: Int,
)
