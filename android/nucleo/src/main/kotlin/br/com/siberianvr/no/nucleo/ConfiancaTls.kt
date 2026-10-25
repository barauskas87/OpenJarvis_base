package br.com.siberianvr.no.nucleo

/** Como o app decide se confia no certificado do Nó. */
sealed interface ConfiancaTls {
    /**
     * Usa as autoridades do sistema (ex.: Let's Encrypt). Se [pinsSpki] não for
     * vazio, a chave pública do servidor também precisa estar na lista
     * (formato "sha256/BASE64", o mesmo do OkHttp).
     */
    data class Sistema(val pinsSpki: List<String> = emptyList()) : ConfiancaTls

    /** Confia somente neste certificado (PEM), p.ex. o autoassinado do Nó em casa. */
    data class CertificadoFixo(val pem: String) : ConfiancaTls
}
