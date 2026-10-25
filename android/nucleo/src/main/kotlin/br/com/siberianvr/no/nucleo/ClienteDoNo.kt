package br.com.siberianvr.no.nucleo

import java.io.ByteArrayInputStream
import java.io.IOException
import java.io.InterruptedIOException
import java.net.SocketTimeoutException
import java.security.cert.CertificateException
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import kotlinx.serialization.SerializationException
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.CertificatePinner
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.tls.HandshakeCertificates

/**
 * Cliente HTTPS do Nó. Chamadas bloqueantes: no Android, rode fora da thread
 * principal (Dispatchers.IO).
 *
 * Regras de segurança:
 * - só https (ver [ConfiguracaoDoNo]), com certificado do sistema + pins ou
 *   com um certificado fixo;
 * - o token só vai no cabeçalho Authorization e nunca aparece em mensagens de erro;
 * - redirecionamentos NÃO são seguidos (o token não pode ir para outro lugar);
 * - o tamanho da resposta é limitado;
 * - POST não é repetido automaticamente (não é idempotente).
 */
class ClienteDoNo internal constructor(
    private val config: ConfiguracaoDoNo,
    private val armazenamento: ArmazenamentoDeToken,
    ajusteParaTeste: ((OkHttpClient.Builder) -> Unit)?,
) {
    constructor(config: ConfiguracaoDoNo, armazenamento: ArmazenamentoDeToken) :
        this(config, armazenamento, null)

    private val json = Json {
        ignoreUnknownKeys = true // o servidor pode ganhar campos sem quebrar o app
        encodeDefaults = false
    }
    private val tipoJson = "application/json; charset=utf-8".toMediaType()
    private val http: OkHttpClient = montar_cliente_http(ajusteParaTeste)

    /** GET /v1/saude (sem token). */
    fun verificar_saude(): RespostaSaude {
        val pedido = Request.Builder().url(url("v1/saude")).get().build()
        val saude = ler_resposta<RespostaSaude>(executar(pedido))
        if (saude.status != "ok") throw ErroDoNo.RespostaInesperada("status")
        return saude
    }

    /** POST /v1/conversar. */
    fun conversar(mensagem: String, conversaId: String? = null): RespostaConversa {
        validar_pedido(mensagem, conversaId)
        val token = token_valido()
        val corpo = json.encodeToString(PedidoConversa(mensagem, conversaId))
        val pedido = Request.Builder()
            .url(url("v1/conversar"))
            .header("Authorization", "Bearer $token")
            .post(corpo.toRequestBody(tipoJson))
            .build()
        return ler_resposta(executar(pedido))
    }

    // ------------------------------------------------------------------ interno

    private fun url(caminho: String) = config.urlBase.newBuilder().addPathSegments(caminho).build()

    private fun validar_pedido(mensagem: String, conversaId: String?) {
        if (mensagem.isBlank()) throw ErroDoNo.PedidoInvalido("Mensagem vazia.")
        // O servidor conta caracteres Unicode (code points), não unidades UTF-16.
        if (mensagem.codePointCount(0, mensagem.length) > TAMANHO_MAX_MENSAGEM) {
            throw ErroDoNo.PedidoInvalido("Mensagem maior que $TAMANHO_MAX_MENSAGEM caracteres.")
        }
        if (conversaId != null && !PADRAO_CONVERSA_ID.matches(conversaId)) {
            throw ErroDoNo.PedidoInvalido("Identificador de conversa inválido.")
        }
    }

    private fun token_valido(): String {
        val token = armazenamento.ler_token()
        if (token.isNullOrBlank()) throw ErroDoNo.SemToken()
        // Validar antes: o OkHttp copia o valor inválido para a mensagem de erro.
        if (!PADRAO_TOKEN.matches(token)) throw ErroDoNo.PedidoInvalido("Token com formato inválido.")
        return token
    }

    private class Bruto(val codigo: Int, val corpo: ByteArray, val esperaSegundos: Long?)

    private fun executar(pedido: Request): Bruto {
        try {
            http.newCall(pedido).execute().use { resposta ->
                val corpo = resposta.body ?: throw ErroDoNo.RespostaInesperada("sem corpo")
                val fonte = corpo.source()
                fonte.request(config.tamanhoMaxRespostaBytes + 1)
                if (fonte.buffer.size > config.tamanhoMaxRespostaBytes) {
                    throw ErroDoNo.RespostaInesperada("resposta grande demais")
                }
                val espera = resposta.header("Retry-After")?.trim()?.toLongOrNull()
                    ?.takeIf { it in 1..3600 }
                return Bruto(resposta.code, fonte.readByteArray(), espera)
            }
        } catch (e: SocketTimeoutException) {
            throw ErroDoNo.TempoEsgotado()
        } catch (e: InterruptedIOException) {
            throw ErroDoNo.TempoEsgotado()
        } catch (e: IOException) {
            throw ErroDoNo.SemConexao(e)
        }
    }

    private inline fun <reified T> ler_resposta(bruto: Bruto): T {
        when (bruto.codigo) {
            200 -> return decodificar(bruto.corpo)
            400 -> throw ErroDoNo.PedidoInvalido("O Nó recusou o formato do pedido.")
            401 -> throw ErroDoNo.NaoAutorizado()
            413 -> throw ErroDoNo.CorpoGrande()
            422 -> throw ErroDoNo.PedidoInvalido(mensagem_do_servidor(bruto) ?: "Pedido inválido.")
            429 -> throw ErroDoNo.LimiteExcedido(bruto.esperaSegundos ?: 1)
            503 -> throw ErroDoNo.NoOcupado(bruto.esperaSegundos ?: 1)
            504 -> throw ErroDoNo.TempoEsgotado()
            else -> throw ErroDoNo.ErroDoServidor(bruto.codigo)
        }
    }

    private inline fun <reified T> decodificar(corpo: ByteArray): T =
        try {
            json.decodeFromString<T>(corpo.toString(Charsets.UTF_8))
        } catch (e: SerializationException) {
            throw ErroDoNo.RespostaInesperada("JSON")
        } catch (e: IllegalArgumentException) {
            throw ErroDoNo.RespostaInesperada("JSON")
        }

    private fun mensagem_do_servidor(bruto: Bruto): String? =
        try {
            json.decodeFromString<RespostaErro>(bruto.corpo.toString(Charsets.UTF_8)).mensagem
                .take(200)
        } catch (e: SerializationException) {
            null
        } catch (e: IllegalArgumentException) {
            null
        }

    private fun montar_cliente_http(ajuste: ((OkHttpClient.Builder) -> Unit)?): OkHttpClient {
        val construtor = OkHttpClient.Builder()
            .connectTimeout(config.tempoConexaoSegundos, TimeUnit.SECONDS)
            .readTimeout(config.tempoLeituraSegundos, TimeUnit.SECONDS)
            .writeTimeout(config.tempoConexaoSegundos, TimeUnit.SECONDS)
            .followRedirects(false)
            .followSslRedirects(false)
            .retryOnConnectionFailure(false)
        when (val confianca = config.confianca) {
            is ConfiancaTls.Sistema -> {
                if (confianca.pinsSpki.isNotEmpty()) {
                    val pinos = CertificatePinner.Builder()
                    pinos.add(config.urlBase.host, *confianca.pinsSpki.toTypedArray())
                    construtor.certificatePinner(pinos.build())
                }
            }
            is ConfiancaTls.CertificadoFixo -> {
                val certificados = HandshakeCertificates.Builder()
                    .addTrustedCertificate(ler_certificado(confianca.pem))
                    .build()
                construtor.sslSocketFactory(certificados.sslSocketFactory(), certificados.trustManager)
            }
        }
        ajuste?.invoke(construtor) // só testes: ex. confiar numa CA de teste mantendo os pins
        return construtor.build()
    }

    private fun ler_certificado(pem: String): X509Certificate =
        try {
            CertificateFactory.getInstance("X.509")
                .generateCertificate(ByteArrayInputStream(pem.toByteArray())) as X509Certificate
        } catch (e: CertificateException) {
            throw IllegalArgumentException("Certificado do Nó inválido.")
        } catch (e: ClassCastException) {
            throw IllegalArgumentException("Certificado do Nó inválido.")
        }

    companion object {
        const val TAMANHO_MAX_MENSAGEM = 8000
        private val PADRAO_CONVERSA_ID = Regex("^[A-Za-z0-9_-]{1,64}$")
        private val PADRAO_TOKEN = Regex("^[A-Za-z0-9._~+/=-]{1,256}$")
    }
}
