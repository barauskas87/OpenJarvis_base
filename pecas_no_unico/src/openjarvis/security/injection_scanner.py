"""Scanner de injeção de prompt (Python puro).

Patch N18: o upstream só tinha padrões em inglês e dependia do Rust quando
disponível. Aqui o scanner é só Python, com padrões em português do Brasil
além dos em inglês, e tolera acentos ausentes ("instrucoes").

Importante: é um ALARME, não uma barreira. Qualquer lista de regex é
contornada por paráfrase. A defesa real é: dado externo entra delimitado,
ferramentas perigosas pedem confirmação e o RBAC nega por padrão.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import List

from openjarvis.security.types import ScanFinding, ThreatLevel

logger = logging.getLogger(__name__)

_MAX_MATCH_CHARS = 100

_ORDEM = [
    ThreatLevel.LOW,
    ThreatLevel.MEDIUM,
    ThreatLevel.HIGH,
    ThreatLevel.CRITICAL,
]

# (regex, nome, nível, descrição). Aplicados sobre o texto normalizado
# (minúsculas, sem acentos), então os padrões em PT-BR não levam acento.
_PADROES = [
    # --- substituição de instruções (EN) ---
    (
        r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)",
        "prompt_override",
        ThreatLevel.HIGH,
        "Attempt to override system instructions",
    ),
    (
        r"disregard\s+(?:all\s+)?(?:previous|prior|your)"
        r"\s+(?:instructions?|programming|rules?)",
        "prompt_override",
        ThreatLevel.HIGH,
        "Attempt to disregard instructions",
    ),
    (
        r"you\s+are\s+now\s+(?:a\s+)?(?:different|new|my)",
        "identity_override",
        ThreatLevel.HIGH,
        "Attempt to change AI identity",
    ),
    # --- substituição de instruções (PT-BR) ---
    (
        r"(?:ignore|ignorar|desconsidere|desconsiderar|esqueca|esquecer)\s+"
        r"(?:todas?\s+)?(?:as\s+|os\s+|suas\s+|seus\s+)?"
        r"(?:instrucoes|regras|ordens|diretrizes|prompts?)"
        r"(?:\s+(?:anteriores|previas|acima|do\s+sistema))?",
        "prompt_override_pt",
        ThreatLevel.HIGH,
        "Tentativa de anular instruções (PT-BR)",
    ),
    (
        r"voce\s+(?:agora\s+)?(?:e|sera|vai\s+ser)\s+(?:um|uma|o|a)?\s*"
        r"(?:outro|outra|novo|nova|diferente)",
        "identity_override_pt",
        ThreatLevel.HIGH,
        "Tentativa de trocar a identidade do assistente (PT-BR)",
    ),
    (
        r"(?:novas?\s+instrucoes|a\s+partir\s+de\s+agora)\s*[:,]",
        "prompt_override_pt",
        ThreatLevel.MEDIUM,
        "Novas instruções injetadas (PT-BR)",
    ),
    # --- execução de comando/código ---
    (
        r"(?:execute|run|eval|execute|executar)\s*\(\s*['\"]",
        "code_injection",
        ThreatLevel.HIGH,
        "Code execution attempt in prompt",
    ),
    (
        r"(?:;|\||&&)\s*(?:rm|curl|wget|nc|ncat|bash|sh|python|perl|powershell)\s",
        "shell_injection",
        ThreatLevel.HIGH,
        "Shell command injection",
    ),
    # --- exfiltração ---
    (
        r"(?:send|post|upload|exfiltrate|transmit)"
        r"\s+(?:(?:to|data|all|everything)\s+)*"
        r"(?:to\s+)?(?:https?://|my\s+server)",
        "exfiltration",
        ThreatLevel.HIGH,
        "Data exfiltration attempt",
    ),
    (
        r"(?:envie|enviar|mande|mandar|poste|postar|suba|subir|transmita)\s+"
        r"(?:\w+\s+){0,4}?(?:para|pra|ao|no)\s+(?:https?://|meu\s+servidor)",
        "exfiltration_pt",
        ThreatLevel.HIGH,
        "Tentativa de exfiltração de dados (PT-BR)",
    ),
    (
        r"base64\s+encode\s+(?:and\s+)?(?:send|include|append)",
        "exfiltration",
        ThreatLevel.MEDIUM,
        "Encoded exfiltration attempt",
    ),
    # --- jailbreak ---
    (
        r"(?:dan|do\s+anything\s+now)\s+(?:mode|prompt|jailbreak)",
        "jailbreak",
        ThreatLevel.HIGH,
        "DAN jailbreak attempt",
    ),
    (
        r"pretend\s+(?:you\s+)?(?:have\s+)?no"
        r"\s+(?:restrictions?|limitations?|rules?|filters?)",
        "jailbreak",
        ThreatLevel.MEDIUM,
        "Restriction bypass attempt",
    ),
    (
        r"(?:finja|simule|aja\s+como\s+se)\s+(?:que\s+)?(?:voce\s+)?"
        r"(?:nao\s+)?(?:tem|tivesse|possui|houvesse)\s+(?:nenhuma\s+)?"
        r"(?:restricoes|limites|regras|filtros)",
        "jailbreak_pt",
        ThreatLevel.MEDIUM,
        "Tentativa de burlar restrições (PT-BR)",
    ),
    # --- delimitadores de papel/modelo ---
    (
        r"```(?:system|assistant)\b",
        "delimiter_injection",
        ThreatLevel.MEDIUM,
        "Role delimiter injection",
    ),
    (
        r"<\|(?:im_start|im_end|system|assistant)\|>",
        "delimiter_injection",
        ThreatLevel.HIGH,
        "Chat template injection",
    ),
    (
        r"</?observation\b|</?observacao\b",
        "delimiter_injection",
        ThreatLevel.HIGH,
        "Tentativa de fechar/forjar o delimitador de observação",
    ),
]


def _normalizar(texto: str) -> str:
    """Minúsculas, sem acentos e com espaços colapsados.

    Mantém o MESMO tamanho em caracteres quando possível: a decomposição NFKD
    só remove marcas combinantes, e os índices dos achados são aproximados
    (servem para exibição, não para recortar o texto original).
    """
    decomposto = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return sem_acento.lower()


@dataclass(slots=True)
class InjectionScanResult:
    """Resultado da varredura."""

    is_clean: bool
    findings: List[ScanFinding]
    threat_level: ThreatLevel  # maior nível encontrado (LOW se limpo)


class InjectionScanner:
    """Procura padrões comuns de injeção de prompt."""

    def __init__(self) -> None:
        self._padroes = [
            (re.compile(p), nome, nivel, desc) for p, nome, nivel, desc in _PADROES
        ]

    def scan(self, text: str) -> InjectionScanResult:
        """Varre ``text`` e devolve os achados."""
        alvo = _normalizar(text)
        achados: List[ScanFinding] = []
        maior = -1
        for regex, nome, nivel, desc in self._padroes:
            for m in regex.finditer(alvo):
                achados.append(
                    ScanFinding(
                        pattern_name=nome,
                        matched_text=m.group(0)[:_MAX_MATCH_CHARS],
                        threat_level=nivel,
                        start=m.start(),
                        end=m.end(),
                        description=desc,
                    )
                )
                maior = max(maior, _ORDEM.index(nivel))
        nivel_final = _ORDEM[maior] if maior >= 0 else ThreatLevel.LOW
        return InjectionScanResult(
            is_clean=not achados, findings=achados, threat_level=nivel_final
        )


__all__ = ["InjectionScanner", "InjectionScanResult"]
