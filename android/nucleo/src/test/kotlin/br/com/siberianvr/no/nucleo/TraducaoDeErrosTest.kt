package br.com.siberianvr.no.nucleo

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class TraducaoDeErrosTest {
    private val todos: List<ErroDoNo> = listOf(
        ErroDoNo.SemToken(),
        ErroDoNo.PedidoInvalido("Mensagem vazia."),
        ErroDoNo.NaoAutorizado(),
        ErroDoNo.LimiteExcedido(9),
        ErroDoNo.NoOcupado(4),
        ErroDoNo.TempoEsgotado(),
        ErroDoNo.CorpoGrande(),
        ErroDoNo.ErroDoServidor(502),
        ErroDoNo.SemConexao(RuntimeException("javax.net.ssl segredo-interno")),
        ErroDoNo.RespostaInesperada("JSON"),
    )

    @Test
    fun todo_erro_tem_texto_em_portugues_nao_vazio() {
        for (erro in todos) assertTrue(TraducaoDeErros.traduzir(erro).isNotBlank(), erro.toString())
    }

    @Test
    fun segundos_aparecem_no_texto() {
        assertTrue("9 s" in TraducaoDeErros.traduzir(ErroDoNo.LimiteExcedido(9)))
        assertTrue("4 s" in TraducaoDeErros.traduzir(ErroDoNo.NoOcupado(4)))
    }

    @Test
    fun causa_tecnica_nao_vaza_para_a_tela() {
        val texto = TraducaoDeErros.traduzir(ErroDoNo.SemConexao(RuntimeException("segredo-interno")))
        assertFalse("segredo-interno" in texto)
    }

    @Test
    fun erro_desconhecido_tem_texto_generico() {
        assertEquals("Algo deu errado.", TraducaoDeErros.traduzir(IllegalStateException("x")))
    }
}
