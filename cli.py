#!/usr/bin/env python3
"""CLI: convierte uno o más PDF/DOCX a Markdown optimizado.

Uso:
    python cli.py archivo1.pdf archivo2.docx -o salida/
    python cli.py carpeta_con_archivos/ -o salida/
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core import BatchProcessor
from core.converter import SUPPORTED_EXTENSIONS


def collect_files(inputs: list[str]) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            files.extend(
                p for p in path.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS
            )
        elif path.is_file():
            files.append(path)
        else:
            print(f"⚠️  Ruta no encontrada, se omite: {item}", file=sys.stderr)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Convierte PDF/DOCX a Markdown optimizado.")
    parser.add_argument("inputs", nargs="+", help="Archivos o carpetas a procesar")
    parser.add_argument("-o", "--output", default="output_md", help="Carpeta de salida")
    parser.add_argument("-w", "--workers", type=int, default=4, help="Hilos concurrentes")
    parser.add_argument("--json", action="store_true", help="Imprime el reporte final en JSON")
    args = parser.parse_args()

    files = collect_files(args.inputs)
    if not files:
        print("No se encontraron archivos .pdf/.docx para procesar.", file=sys.stderr)
        return 1

    processor = BatchProcessor(max_workers=args.workers)
    report = processor.process(files, args.output)
    summary = report.as_summary_dict()

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(f"\n✅ {summary['succeeded']} convertidos | ❌ {summary['failed']} fallidos")
        print(f"💰 Tokens ahorrados por optimización: {summary['total_tokens_saved']}\n")
        for detail in summary["details"]:
            if detail["success"]:
                print(
                    f"  ✓ {detail['file']} -> {detail['output']} "
                    f"({detail['raw_tokens']} → {detail['optimized_tokens']} tokens, "
                    f"-{detail['savings_percent']}%)"
                )
            else:
                print(f"  ✗ {detail['file']}: [{detail['error_type']}] {detail['error_detail']}")

    return 0 if summary["failed"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
