package br.com.siberianvr.no.app

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun TelaDeConversa(modelo: ConversaViewModel, aoAbrirConfiguracao: () -> Unit) {
    val estado by modelo.estado.collectAsState()
    var texto by remember { mutableStateOf("") }

    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("Nó Único", style = MaterialTheme.typography.titleLarge)
            Row {
                TextButton(onClick = modelo::nova_conversa) { Text("Nova") }
                TextButton(onClick = aoAbrirConfiguracao) { Text("Configurar") }
            }
        }
        LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            items(estado.mensagens) { m ->
                Text(
                    text = (if (m.deUsuario) "Você: " else "Nó: ") + m.texto,
                    style = MaterialTheme.typography.bodyLarge,
                )
            }
        }
        estado.erro?.let {
            Text(it, color = MaterialTheme.colorScheme.error)
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                value = texto,
                onValueChange = { texto = it },
                modifier = Modifier.weight(1f),
                label = { Text("Mensagem") },
                enabled = !estado.carregando,
            )
            Button(
                onClick = {
                    modelo.enviar_mensagem(texto)
                    texto = ""
                },
                enabled = !estado.carregando && texto.isNotBlank(),
            ) { Text(if (estado.carregando) "…" else "Enviar") }
        }
    }
}
