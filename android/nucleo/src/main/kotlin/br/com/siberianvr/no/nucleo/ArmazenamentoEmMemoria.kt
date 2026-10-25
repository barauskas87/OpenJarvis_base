package br.com.siberianvr.no.nucleo

import java.util.concurrent.atomic.AtomicReference

/** Implementação sem persistência, para testes e para a linha de comando. */
class ArmazenamentoEmMemoria(inicial: String? = null) : ArmazenamentoDeToken {
    private val guardado = AtomicReference(inicial)

    override fun ler_token(): String? = guardado.get()

    override fun gravar_token(token: String) = guardado.set(token)

    override fun apagar_token() = guardado.set(null)
}
