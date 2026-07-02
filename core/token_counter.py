"""Conteo de tokens estilo GPT/Claude para reportar el ahorro de la optimización.

Usamos tiktoken (cl100k_base) como aproximación estándar de la industria.
No es el tokenizador exacto de Claude, pero es la referencia más usada
para estimar costo de tokens de forma consistente y reproducible.

NOTA DE DESPLIEGUE: tiktoken descarga su tabla BPE desde internet la
primera vez que se usa un encoding (openaipublic.blob.core.windows.net).
En hosts serverless gratuitos con egress restringido (o con cold starts
sin red aún lista) esa descarga puede fallar. Por eso este módulo cae a
una aproximación local (heurística de caracteres/token) en vez de tumbar
la conversión entera por un problema de red ajeno al documento.
Para evitar la descarga en runtime, precachear el encoding en build time:
    python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"
y setear TIKTOKEN_CACHE_DIR a un directorio persistente del build.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

logger = logging.getLogger("md_converter.tokens")

_CHARS_PER_TOKEN_APPROX = 4.0  # heurística estándar para texto en inglés/español mixto


@lru_cache(maxsize=1)
def _encoder():
    try:
        import tiktoken

        return tiktoken.get_encoding("cl100k_base")
    except Exception as exc:  # noqa: BLE001 - típicamente red no disponible
        logger.warning(
            "No se pudo cargar tiktoken (%s). Usando conteo aproximado de tokens.", exc
        )
        return None


def count_tokens(text: str) -> int:
    encoder = _encoder()
    if encoder is not None:
        return len(encoder.encode(text))
    # Fallback sin red: aproximación por longitud de caracteres.
    return max(1, int(len(text) / _CHARS_PER_TOKEN_APPROX)) if text else 0


@dataclass
class TokenSavingsReport:
    raw_tokens: int
    optimized_tokens: int

    @property
    def tokens_saved(self) -> int:
        return max(self.raw_tokens - self.optimized_tokens, 0)

    @property
    def savings_percent(self) -> float:
        if self.raw_tokens == 0:
            return 0.0
        return round((self.tokens_saved / self.raw_tokens) * 100, 2)

    def as_dict(self) -> dict:
        return {
            "raw_tokens": self.raw_tokens,
            "optimized_tokens": self.optimized_tokens,
            "tokens_saved": self.tokens_saved,
            "savings_percent": self.savings_percent,
        }


def build_savings_report(raw_markdown: str, optimized_markdown: str) -> TokenSavingsReport:
    return TokenSavingsReport(
        raw_tokens=count_tokens(raw_markdown),
        optimized_tokens=count_tokens(optimized_markdown),
    )
