"""Limpieza y compactación del Markdown crudo generado por markitdown.

Objetivo: reducir tokens (espacios, líneas repetidas, decoraciones
innecesarias) SIN alterar el significado del contenido. No se toca
el texto de párrafos, solo el "ruido" estructural que suele venir
de PDFs (headers/footers repetidos, saltos de página, whitespace).
"""
from __future__ import annotations

import re

# Líneas cortas que se repiten en >= este número de páginas se consideran
# headers/footers de PDF (ej. "Página 3 de 40", nombre de la empresa, etc.)
_MIN_REPEATS_TO_STRIP = 3
_MAX_LEN_FOR_BOILERPLATE = 80


class MarkdownOptimizer:
    def optimize(self, raw_markdown: str) -> str:
        text = raw_markdown

        text = self._strip_repeated_boilerplate_lines(text)
        text = self._collapse_whitespace(text)
        text = self._normalize_headers(text)
        text = self._dedupe_blank_lines(text)
        text = self._trim_lines(text)
        text = self._collapse_empty_links_and_images(text)

        return text.strip() + "\n"

    # ------------------------------------------------------------------ #

    @staticmethod
    def _strip_repeated_boilerplate_lines(text: str) -> str:
        """Elimina líneas cortas que se repiten muchas veces (headers/footers)."""
        lines = text.split("\n")
        counts: dict[str, int] = {}
        for line in lines:
            stripped = line.strip()
            if stripped and len(stripped) <= _MAX_LEN_FOR_BOILERPLATE:
                counts[stripped] = counts.get(stripped, 0) + 1

        boilerplate = {
            line for line, n in counts.items() if n >= _MIN_REPEATS_TO_STRIP
        }
        if not boilerplate:
            return text

        return "\n".join(line for line in lines if line.strip() not in boilerplate)

    @staticmethod
    def _collapse_whitespace(text: str) -> str:
        # Tabs y espacios múltiples -> un solo espacio (preserva indentación de código si existiera)
        text = re.sub(r"[ \t]+", " ", text)
        return text

    @staticmethod
    def _normalize_headers(text: str) -> str:
        # "#Título" -> "# Título" (markitdown a veces omite el espacio)
        return re.sub(r"^(#{1,6})([^\s#])", r"\1 \2", text, flags=re.MULTILINE)

    @staticmethod
    def _dedupe_blank_lines(text: str) -> str:
        # 3+ saltos de línea consecutivos -> 2 (un párrafo de separación, no más)
        return re.sub(r"\n{3,}", "\n\n", text)

    @staticmethod
    def _trim_lines(text: str) -> str:
        return "\n".join(line.rstrip() for line in text.split("\n"))

    @staticmethod
    def _collapse_empty_links_and_images(text: str) -> str:
        # Elimina imágenes/links vacíos que markitdown a veces deja de artefactos OCR
        text = re.sub(r"!\[\]\(\s*\)", "", text)
        text = re.sub(r"\[\]\(\s*\)", "", text)
        return text
