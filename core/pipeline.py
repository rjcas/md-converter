"""Orquesta un único archivo a través de: conversión -> optimización -> métricas.

Es la unidad que batch_processor.py paraleliza. Se mantiene sin estado
compartido mutable para que sea segura en ThreadPoolExecutor.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .converter import MarkitdownConverter
from .exceptions import ConversionError
from .optimizer import MarkdownOptimizer
from .token_counter import TokenSavingsReport, build_savings_report


@dataclass
class DocumentResult:
    source_path: Path
    success: bool
    optimized_markdown: str | None = None
    output_path: Path | None = None
    token_report: TokenSavingsReport | None = None
    error_type: str | None = None
    error_detail: str | None = None

    def as_summary_dict(self) -> dict:
        base = {
            "file": self.source_path.name,
            "success": self.success,
        }
        if self.success:
            base["output"] = str(self.output_path)
            base.update(self.token_report.as_dict())
        else:
            base["error_type"] = self.error_type
            base["error_detail"] = self.error_detail
        return base


class ConversionPipeline:
    def __init__(self) -> None:
        self._converter = MarkitdownConverter()
        self._optimizer = MarkdownOptimizer()

    def run(self, file_path: str | Path, output_dir: str | Path) -> DocumentResult:
        source_path = Path(file_path)
        try:
            raw = self._converter.convert(source_path)
            optimized_text = self._optimizer.optimize(raw.raw_markdown)
            report = build_savings_report(raw.raw_markdown, optimized_text)

            output_path = self._write_output(source_path, optimized_text, output_dir)

            return DocumentResult(
                source_path=source_path,
                success=True,
                optimized_markdown=optimized_text,
                output_path=output_path,
                token_report=report,
            )
        except ConversionError as exc:
            return DocumentResult(
                source_path=source_path,
                success=False,
                error_type=type(exc).__name__,
                error_detail=exc.detail,
            )
        except Exception as exc:  # noqa: BLE001 - red de seguridad: nunca tumbar el batch
            return DocumentResult(
                source_path=source_path,
                success=False,
                error_type="UnexpectedError",
                error_detail=str(exc),
            )

    @staticmethod
    def _write_output(source_path: Path, content: str, output_dir: str | Path) -> Path:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"{source_path.stem}.md"
        output_path.write_text(content, encoding="utf-8")
        return output_path
