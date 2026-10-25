plugins {
    kotlin("jvm")
    kotlin("plugin.serialization")
}

// Gera bytecode Java 17 (o que o app Android usa), mesmo compilando com JDK mais novo.
java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

dependencies {
    api("com.squareup.okhttp3:okhttp:4.12.0")
    api("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    implementation("com.squareup.okhttp3:okhttp-tls:4.12.0")

    testImplementation(kotlin("test"))
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
}

tasks.test {
    useJUnitPlatform()
    // Os mesmos arquivos de contrato que os testes do servidor Python leem.
    systemProperty("contrato.dir", rootProject.projectDir.resolve("../contrato").canonicalPath)
    // Teste de ponta a ponta com o servidor Python real (opcional).
    systemProperty("no.python", System.getenv("NO_PYTHON") ?: "")
    systemProperty("no.pecas", rootProject.projectDir.resolve("../pecas_no_unico").canonicalPath)
    testLogging { events("failed", "skipped") }
}
