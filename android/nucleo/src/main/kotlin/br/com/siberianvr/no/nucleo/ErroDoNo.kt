package br.com.siberianvr.no.nucleo

/**
 * Erros do cliente. As mensagens nunca contêm o token nem o corpo enviado,
 * para não vazarem em logs ou telas de erro.
 */
sealed class ErroDoNo(mensagem: String, causa: Throwable? = null) : Exception(mensagem, causa) {
    /** Não há token guardado no aparelho. */
    class SemToken : ErroDoNo("Nenhum token configurado.")

    /** Pedido recusado antes de sair do aparelho (ou 422 do servidor). */
    class PedidoInvalido(detalhe: String) : ErroDoNo(detalhe)

    /** 401: token errado, revogado ou ausente. */
    class NaoAutorizado : ErroDoNo("Token não aceito pelo Nó.")

    /** 429: aguarde [segundos]. */
    class LimiteExcedido(val segundos: Long) : ErroDoNo("Muitos pedidos; aguarde $segundos s.")

    /** 503: o Nó está ocupado. */
    class NoOcupado(val segundos: Long) : ErroDoNo("Nó ocupado; tente em $segundos s.")

    /** 504 ou tempo de leitura esgotado. */
    class TempoEsgotado : ErroDoNo("A resposta demorou demais.")

    /** 413: mensagem maior do que o Nó aceita. */
    class CorpoGrande : ErroDoNo("Mensagem grande demais.")

    /** 5xx e respostas de intermediários (proxy, balanceador). */
    class ErroDoServidor(val codigoHttp: Int) : ErroDoNo("Falha no Nó (HTTP $codigoHttp).")

    /** Sem rede, recusa de conexão, certificado não confiável ou pin incorreto. */
    class SemConexao(causa: Throwable) : ErroDoNo("Não foi possível falar com o Nó com segurança.", causa)

    /** Resposta que não segue o contrato. */
    class RespostaInesperada(motivo: String) : ErroDoNo("Resposta fora do contrato: $motivo.")
}
