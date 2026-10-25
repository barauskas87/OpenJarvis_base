package br.com.siberianvr.no.nucleo

import java.io.File
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate

/** Servidor HTTPS de mentira com certificado próprio (autoassinado). */
class NoDeMentira(hostSan: String = "localhost") : AutoCloseable {
    val certificado: HeldCertificate = HeldCertificate.Builder()
        .addSubjectAlternativeName(hostSan)
        .commonName("no-de-mentira")
        .build()
    val servidor = MockWebServer()

    init {
        val certs = HandshakeCertificates.Builder().heldCertificate(certificado).build()
        servidor.useHttps(certs.sslSocketFactory(), false)
        servidor.start()
    }

    val url: String get() = "https://localhost:${servidor.port}/"
    val pem: String get() = certificado.certificatePem()

    fun config(
        confianca: ConfiancaTls = ConfiancaTls.CertificadoFixo(pem),
        tempoLeitura: Long = 10,
        tamanhoMax: Long = 1_048_576,
    ) = ConfiguracaoDoNo(
        url,
        confianca,
        tempoLeituraSegundos = tempoLeitura,
        tamanhoMaxRespostaBytes = tamanhoMax,
    )

    fun cliente(
        token: String? = "nu_tokenDeTeste123",
        config: ConfiguracaoDoNo = config(),
    ) = ClienteDoNo(config, ArmazenamentoEmMemoria(token))

    override fun close() = servidor.close()
}

const val TOKEN_DE_TESTE = "nu_tokenDeTeste123"

/** Lê um arquivo da pasta contrato/ (a mesma que os testes Python usam). */
fun ler_contrato(nome: String): String {
    val pasta = System.getProperty("contrato.dir") ?: error("contrato.dir não definido")
    return File(pasta, nome).readText(Charsets.UTF_8)
}

val RESPOSTA_OK = """{"resposta":"ok","conversa_id":"c1","turnos":1}"""
