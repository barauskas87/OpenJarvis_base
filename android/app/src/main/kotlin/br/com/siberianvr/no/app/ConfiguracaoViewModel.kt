package br.com.siberianvr.no.app

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import br.com.siberianvr.no.nucleo.ConfiguracaoDoNo
import br.com.siberianvr.no.nucleo.TraducaoDeErros
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class EstadoDaConfiguracao(
    val url: String = "",
    val certificadoPem: String = "",
    val token: String = "", // nunca preenchido a partir do armazenamento
    val mensagem: String? = null,
    val testando: Boolean = false,
)

class ConfiguracaoViewModel(private val conteiner: Conteiner) : ViewModel() {
    private val _estado = MutableStateFlow(
        EstadoDaConfiguracao(
            url = conteiner.configuracao.url(),
            certificadoPem = conteiner.configuracao.certificado_pem(),
        ),
    )
    val estado: StateFlow<EstadoDaConfiguracao> = _estado.asStateFlow()

    fun alterar_url(valor: String) = _estado.update { it.copy(url = valor) }

    fun alterar_certificado(valor: String) = _estado.update { it.copy(certificadoPem = valor) }

    fun alterar_token(valor: String) = _estado.update { it.copy(token = valor) }

    /** Valida, grava e (se informado) troca o token. */
    fun salvar() {
        val atual = _estado.value
        try {
            ConfiguracaoDoNo(atual.url) // só para validar (https obrigatório)
        } catch (e: IllegalArgumentException) {
            _estado.update { it.copy(mensagem = e.message ?: "Endereço inválido.") }
            return
        }
        conteiner.configuracao.gravar(atual.url, atual.certificadoPem)
        if (atual.token.isNotBlank()) {
            conteiner.armazenamento.gravar_token(atual.token.trim())
        }
        _estado.update { it.copy(token = "", mensagem = "Configuração salva.") }
    }

    fun testar_conexao() {
        val cliente = conteiner.criar_cliente()
        if (cliente == null) {
            _estado.update { it.copy(mensagem = "Salve um endereço válido primeiro.") }
            return
        }
        _estado.update { it.copy(testando = true, mensagem = null) }
        viewModelScope.launch {
            val r = withContext(Dispatchers.IO) { runCatching { cliente.verificar_saude() } }
            _estado.update {
                it.copy(
                    testando = false,
                    mensagem = r.fold(
                        onSuccess = { s -> "Conectado ao Nó (API v${s.versaoApi})." },
                        onFailure = { e -> TraducaoDeErros.traduzir(e) },
                    ),
                )
            }
        }
    }

    fun apagar_token() {
        conteiner.armazenamento.apagar_token()
        _estado.update { it.copy(mensagem = "Token apagado deste aparelho.") }
    }
}
