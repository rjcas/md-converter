"""API HTTP del conversor.

IMPORTANTE (ver README): Netlify Functions no ejecuta runtimes Python de
forma nativa para lógica de servidor arbitraria (sí soporta Python en el
*build* de sitios estáticos, que es otra cosa). Este servicio se despliega
en un host Python gratuito (Render, Railway, Fly.io, HF Spaces) y el
frontend estático en Netlify lo consume vía fetch(). CORS ya está
habilitado para ese escenario.

Endpoints:
    POST /convert        -> un archivo, devuelve el .md para descargar
    POST /convert-batch  -> varios archivos, devuelve un .zip con los .md
    GET  /health          -> healthcheck
"""
from __future__ import annotations

import io
import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from core import ConversionPipeline, BatchProcessor
from core.converter import SUPPORTED_EXTENSIONS

app = FastAPI(title="PDF/DOCX a Markdown Optimizado", version="1.0.0")

# ALLOWED_ORIGIN se setea como env var en el host (ver render.yaml).
# Default "*" solo para desarrollo local; en producción usar el dominio
# real de Netlify (ej. "https://tu-app.netlify.app").
_allowed_origin = os.environ.get("ALLOWED_ORIGIN", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_allowed_origin] if _allowed_origin != "*" else ["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/convert")
async def convert_single(file: UploadFile = File(...)) -> Response:
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"Formato no soportado: {suffix}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / file.filename
        tmp_path.write_bytes(await file.read())

        pipeline = ConversionPipeline()
        result = pipeline.run(tmp_path, output_dir=tmp)

        if not result.success:
            raise HTTPException(422, f"[{result.error_type}] {result.error_detail}")

        return Response(
            content=result.optimized_markdown,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="{tmp_path.stem}.md"',
                # Header custom con las métricas de ahorro para que el frontend las lea
                "X-Token-Report": _compact_json(result.token_report.as_dict()),
                "Access-Control-Expose-Headers": "X-Token-Report, Content-Disposition",
            },
        )


@app.post("/convert-batch")
async def convert_batch(files: list[UploadFile] = File(...)) -> Response:
    with tempfile.TemporaryDirectory() as tmp_in, tempfile.TemporaryDirectory() as tmp_out:
        saved_paths = []
        for f in files:
            suffix = Path(f.filename).suffix.lower()
            if suffix not in SUPPORTED_EXTENSIONS:
                continue  # se reporta como "no procesado" implícitamente en el resumen
            path = Path(tmp_in) / f.filename
            path.write_bytes(await f.read())
            saved_paths.append(path)

        if not saved_paths:
            raise HTTPException(400, "Ningún archivo tiene formato soportado (.pdf/.docx)")

        report = BatchProcessor(max_workers=4).process(saved_paths, tmp_out)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for result in report.succeeded:
                zf.write(result.output_path, arcname=result.output_path.name)
            zf.writestr("_reporte_conversion.json", _compact_json(report.as_summary_dict()))

        zip_buffer.seek(0)
        return Response(
            content=zip_buffer.read(),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="markdown_convertido.zip"'},
        )


def _compact_json(data: dict) -> str:
    import json

    return json.dumps(data, ensure_ascii=False)
