package br.com.siberianvr.no.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val conteiner = Conteiner(this)
        setContent {
            MaterialTheme {
                var naConfiguracao by remember { mutableStateOf(conteiner.criar_cliente() == null) }
                val conversa: ConversaViewModel = viewModel(
                    factory = viewModelFactory { initializer { ConversaViewModel(conteiner::criar_cliente) } },
                )
                val configuracao: ConfiguracaoViewModel = viewModel(
                    factory = viewModelFactory { initializer { ConfiguracaoViewModel(conteiner) } },
                )
                if (naConfiguracao) {
                    TelaDeConfiguracao(configuracao, aoVoltar = { naConfiguracao = false })
                } else {
                    TelaDeConversa(conversa, aoAbrirConfiguracao = { naConfiguracao = true })
                }
            }
        }
    }
}
