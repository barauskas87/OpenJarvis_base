package br.com.siberianvr.no.app

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import br.com.siberianvr.no.nucleo.ArmazenamentoDeToken
import java.security.GeneralSecurityException
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Guarda o token cifrado (AES-256-GCM). A chave fica no Android Keystore e nunca
 * sai dele; no disco só vão o vetor (iv) e o texto cifrado.
 */
class ArmazenamentoSeguroAndroid(contexto: Context) : ArmazenamentoDeToken {
    private val preferencias = contexto.getSharedPreferences("no_token", Context.MODE_PRIVATE)

    override fun ler_token(): String? {
        val iv = preferencias.getString(CAMPO_IV, null) ?: return null
        val cifrado = preferencias.getString(CAMPO_CIFRADO, null) ?: return null
        return try {
            val cifra = Cipher.getInstance(TRANSFORMACAO)
            cifra.init(
                Cipher.DECRYPT_MODE,
                chave(),
                GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)),
            )
            String(cifra.doFinal(Base64.decode(cifrado, Base64.NO_WRAP)), Charsets.UTF_8)
        } catch (e: GeneralSecurityException) {
            // Chave perdida (ex.: restauração do aparelho): o token não é recuperável.
            apagar_token()
            null
        }
    }

    override fun gravar_token(token: String) {
        val cifra = Cipher.getInstance(TRANSFORMACAO)
        cifra.init(Cipher.ENCRYPT_MODE, chave())
        val cifrado = cifra.doFinal(token.toByteArray(Charsets.UTF_8))
        preferencias.edit()
            .putString(CAMPO_IV, Base64.encodeToString(cifra.iv, Base64.NO_WRAP))
            .putString(CAMPO_CIFRADO, Base64.encodeToString(cifrado, Base64.NO_WRAP))
            .apply()
    }

    override fun apagar_token() {
        preferencias.edit().clear().apply()
    }

    private fun chave(): SecretKey {
        val repositorio = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (repositorio.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val gerador = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gerador.init(
            KeyGenParameterSpec.Builder(
                ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return gerador.generateKey()
    }

    private companion object {
        const val ALIAS = "no_unico_token"
        const val TRANSFORMACAO = "AES/GCM/NoPadding"
        const val CAMPO_IV = "iv"
        const val CAMPO_CIFRADO = "cifrado"
    }
}
