package br.com.siberianvr.no.nucleo

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** Corpo de POST /v1/conversar. Deve espelhar contrato/pedido_conversar.json. */
@Serializable
data class PedidoConversa(
    val mensagem: String,
    @SerialName("conversa_id") val conversaId: String? = null,
)
