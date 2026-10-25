pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
        google()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
        google()
    }
}

rootProject.name = "no-unico-android"

// Núcleo: Kotlin/JVM puro (cliente HTTPS do Nó). Compila e testa em qualquer máquina com JDK.
include(":nucleo")

// App: só entra quando existe Android SDK na máquina. Nesse caso o projeto raiz usa
// build.android.gradle.kts (todos os plugins declarados juntos, como o Android exige);
// sem SDK usa build.gradle.kts (só JVM), que não precisa baixar nada do Google.
val temAndroidSdk = !System.getenv("ANDROID_HOME").isNullOrBlank() ||
    !System.getenv("ANDROID_SDK_ROOT").isNullOrBlank() ||
    file("local.properties").exists()
if (temAndroidSdk) {
    rootProject.buildFileName = "build.android.gradle.kts"
    include(":app")
}
