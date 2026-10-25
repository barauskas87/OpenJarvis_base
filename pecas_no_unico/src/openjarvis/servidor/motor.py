"""Motor de inferência concreto (servidor compatível com a API da OpenAI)."""

from __future__ import annotations

from openjarvis.engine._openai_compat import _OpenAICompatibleEngine


class MotorOpenAICompativel(_OpenAICompatibleEngine):
    """Fala com vLLM, llama.cpp, Ollama (/v1) ou similar."""

    engine_id = "openai-compat"
