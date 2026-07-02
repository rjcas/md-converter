"""Procesamiento por lotes: N archivos -> N resultados, sin que un error tumbe el resto.

Usa ThreadPoolExecutor porque el trabajo es I/O-bound (lectura de disco,
parsing de PDF/DOCX libera el GIL en las partes C de las libs subyacentes).
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from .pipeline import ConversionPipeline, DocumentResult

logger = logging.getLogger("md_converter.batch")

DEFAULT_MAX_WORKERS = 4  # conservador: entornos serverless gratuitos tienen CPU/RAM limitados


@dataclass
class BatchReport:
    results: list[DocumentResult] = field(default_factory=list)

    @property
    def succeeded(self) -> list[DocumentResult]:
        return [r for r in self.results if r.success]

    @property
    def failed(self) -> list[DocumentResult]:
        return [r for r in self.results if not r.success]

    @property
    def total_tokens_saved(self) -> int:
        return sum(r.token_report.tokens_saved for r in self.succeeded)

    def as_summary_dict(self) -> dict:
        return {
            "total_files": len(self.results),
            "succeeded": len(self.succeeded),
            "failed": len(self.failed),
            "total_tokens_saved": self.total_tokens_saved,
            "details": [r.as_summary_dict() for r in self.results],
        }


class BatchProcessor:
    def __init__(self, max_workers: int = DEFAULT_MAX_WORKERS) -> None:
        self._max_workers = max_workers

    def process(
        self,
        file_paths: list[str | Path],
        output_dir: str | Path,
    ) -> BatchReport:
        report = BatchReport()

        # Una pipeline por worker thread evitaría contención; para simplicidad
        # y porque MarkItDown() es liviano, se comparte una instancia por tarea.
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {
                executor.submit(self._run_single, path, output_dir): path
                for path in file_paths
            }
            for future in as_completed(futures):
                path = futures[future]
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001 - último resguardo del batch
                    logger.error("Fallo inesperado no capturado para %s: %s", path, exc)
                    result = DocumentResult(
                        source_path=Path(path),
                        success=False,
                        error_type="UnexpectedError",
                        error_detail=str(exc),
                    )
                report.results.append(result)

        return report

    @staticmethod
    def _run_single(file_path: str | Path, output_dir: str | Path) -> DocumentResult:
        # Se instancia por tarea: evita compartir estado de MarkItDown entre threads.
        pipeline = ConversionPipeline()
        return pipeline.run(file_path, output_dir)
