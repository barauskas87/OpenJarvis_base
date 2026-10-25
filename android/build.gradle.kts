// Plugins do núcleo (JVM puro). O módulo :app declara os do Android por conta própria,
// para o núcleo compilar em máquinas sem acesso ao repositório do Google.
plugins {
    kotlin("jvm") version "2.0.21" apply false
    kotlin("plugin.serialization") version "2.0.21" apply false
}
