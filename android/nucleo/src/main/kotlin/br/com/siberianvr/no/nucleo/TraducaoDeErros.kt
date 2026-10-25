package br.com.siberianvr.no.nucleo

/** Texto em português para mostrar ao usuário. Sem detalhes técnicos nem dados sensíveis. */
object TraducaoDeErros {
    fun traduzir(erro: Throwable): String =
        when (erro) {
            is ErroDoNo.SemToken -> "Configure o token do seu Nó nas configurações."
            is ErroDoNo.NaoAutorizado -> "O Nó não aceitou o seu token. Gere um novo e atualize nas configurações."
            is ErroDoNo.LimiteExcedido -> "Muitos pedidos seguidos. Tente de novo em ${erro.segundos} s."
            is ErroDoNo.NoOcupado -> "O Nó está ocupado. Tente de novo em ${erro.segundos} s."
            is ErroDoNo.TempoEsgotado -> "O Nó demorou demais para responder."
            is ErroDoNo.CorpoGrande -> "A mensagem é grande demais."
            is ErroDoNo.PedidoInvalido -> erro.message ?: "Pedido inválido."
            is ErroDoNo.ErroDoServidor -> "O Nó falhou (código ${erro.codigoHttp})."
            is ErroDoNo.SemConexao ->
                "Não consegui falar com o Nó com segurança. Confira o endereço, a rede e o certificado."
            is ErroDoNo.RespostaInesperada -> "O Nó respondeu algo que o app não entende. Atualize o app."
            else -> "Algo deu errado."
        }
}
