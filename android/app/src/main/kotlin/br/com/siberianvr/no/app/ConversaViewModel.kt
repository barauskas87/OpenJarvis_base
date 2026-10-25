package br.com.siberianvr.no.app

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import br.com.siberianvr.no.nucleo.ClienteDoNo
import br.com.siberianvr.no.nucleo.TraducaoDeErros
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class MensagemNaTela(val deUsuario: Boolean, val texto: String)

data class EstadoDaConversa(
    val mensagens: List<MensagemNaTela> = emptyList(),
    val carregando: Boolean = false,
    val erro: String? = null,
    val conversaId: String? = null,
)

class ConversaViewModel(private val fabricaDeCliente: () -> ClienteDoNo?) : ViewModel() {
    private val _estado = MutableStateFlow(EstadoDaConversa())
    val estado: StateFlow<EstadoDaConversa> = _estado.asStateFlow()

    fun enviar_mensagem(texto: String) {
        if (texto.isBlank() || _estado.value.carregando) return
        val cliente = fabricaDeCliente()
        if (cliente == null) {
            _estado.update { it.copy(erro = "Configure o endereço e o token do Nó.") }
            return
        }
        val conversaId = _estado.value.conversaId
        _estado.update {
            it.copy(
                mensagens = it.mensagens + MensagemNaTela(true, texto),
                carregando = true,
                erro = null,
            )
        }
        viewModelScope.launch {
            // Chamada de rede bloqueante: sempre fora da thread principal.
            val resultado = withContext(Dispatchers.IO) {
                runCatching { cliente.conversar(texto, conversaId) }
            }
            resultado
                .onSuccess { r ->
                    _estado.update {
                        it.copy(
                            mensagens = it.mensagens + MensagemNaTela(false, r.resposta),
                            carregando = false,
                            conversaId = r.conversaId,
                        )
                    }
                }
                .onFailure { e ->
                    _estado.update { it.copy(carregando = false, erro = TraducaoDeErros.traduzir(e)) }
                }
        }
    }

    fun limpar_erro() = _estado.update { it.copy(erro = null) }

    fun nova_conversa() = _estado.update { EstadoDaConversa() }
}
