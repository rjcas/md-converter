"""Excepciones específicas del pipeline de conversión.

Separar los tipos de error permite que batch_processor.py decida,
por archivo, si reintentar, saltar o abortar — sin parsear strings.
"""


class ConversionError(Exception):
    """Error base. Todas las excepciones del pipeline heredan de acá."""

    def __init__(self, file_path: str, detail: str):
        self.file_path = file_path
        self.detail = detail
        super().__init__(f"[{file_path}] {detail}")


class UnsupportedFormatError(ConversionError):
    """Extensión no soportada (no es .pdf ni .docx)."""


class CorruptFileError(ConversionError):
    """El archivo existe pero markitdown/las libs de fallback no pudieron parsearlo."""


class FileLockedError(ConversionError):
    """El archivo está bloqueado por otro proceso (típico en Windows con Office abierto)."""


class EmptyContentError(ConversionError):
    """La conversión produjo texto vacío o solo whitespace (posible PDF escaneado sin OCR)."""
