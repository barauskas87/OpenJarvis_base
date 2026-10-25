# memory — ADAPTADO
Cobertura: [V] + `store.py:22-40`. Store de fatos em SQLite, lock de arquivo com `fcntl` (POSIX) e fallback Windows (`store.py:29,34-40`). Sem rede/subprocess. Útil. Ler `service.py` e `extractor.py` (usa LLM) antes.
