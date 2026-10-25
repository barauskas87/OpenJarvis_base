package br.com.siberianvr.no.app

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp

@Composable
fun TelaDeConfiguracao(modelo: ConfiguracaoViewModel, aoVoltar: () -> Unit) {
    val estado by modelo.estado.collectAsState()

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Configuração do Nó", style = MaterialTheme.typography.titleLarge)
        OutlinedTextField(
            value = estado.url,
            onValueChange = modelo::alterar_url,
            label = { Text("Endereço (https://…)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = estado.token,
            onValueChange = modelo::alterar_token,
            label = { Text("Token (deixe vazio para manter o atual)") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = estado.certificadoPem,
            onValueChange = modelo::alterar_certificado,
            label = { Text("Certificado do Nó (PEM; vazio = autoridades do sistema)") },
            minLines = 4,
            modifier = Modifier.fillMaxWidth(),
        )
        estado.mensagem?.let { Text(it) }
        Button(onClick = modelo::salvar, modifier = Modifier.fillMaxWidth()) { Text("Salvar") }
        OutlinedButton(
            onClick = modelo::testar_conexao,
            enabled = !estado.testando,
            modifier = Modifier.fillMaxWidth(),
        ) { Text(if (estado.testando) "Testando…" else "Testar conexão") }
        OutlinedButton(onClick = modelo::apagar_token, modifier = Modifier.fillMaxWidth()) {
            Text("Apagar token deste aparelho")
        }
        OutlinedButton(onClick = aoVoltar, modifier = Modifier.fillMaxWidth()) { Text("Voltar") }
    }
}
