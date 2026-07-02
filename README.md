# PDF/DOCX → Markdown Optimizado

Convierte PDF y DOCX a Markdown limpio y optimizado en tokens, usando
`markitdown` (Microsoft) como motor principal, con fallbacks propios
(`python-docx`, `pdfplumber`) para archivos que markitdown rechaza.

## ⚠️ Nota crítica de arquitectura: Netlify y Python

**Netlify Functions no ejecuta un runtime Python arbitrario.** Soporta
Python en el *build* de sitios estáticos (generar HTML con MkDocs, etc.),
pero las Functions de servidor son Node.js/TypeScript o Go — no hay forma
soportada de correr `markitdown` (que depende de `pdfminer`, `mammoth`,
etc.) dentro de una Netlify Function. Intentarlo vía subproceso
(`spawn python`) falla en producción porque no hay intérprete Python en
ese entorno de ejecución.

**Arquitectura recomendada (100% gratuita):**

```
┌─────────────────────┐        fetch()        ┌──────────────────────────┐
│   Netlify (frontend)  │  ───────────────────▶ │  Backend Python (FastAPI) │
│   HTML/JS estático,    │                        │  Render / Railway / Fly.io│
│   drag&drop, descarga  │  ◀─────────────────── │  / HF Spaces (free tier)  │
└─────────────────────┘     .md o .zip + JSON   └──────────────────────────┘
```

- **Netlify**: sirve el frontend estático (formulario de subida, botón de
  descarga, panel de ahorro de tokens). Costo: $0.
- **Backend** (`api/app.py`, FastAPI): corre este pipeline. Cualquier free
  tier con runtime Python real sirve — Render, Railway, Fly.io, Hugging
  Face Spaces. Costo: $0 en el tier gratuito de cualquiera de esos.

Si el requisito de "todo en Netlify" es innegociable, la única vía real
es reescribir el motor de conversión en JS/TS (perdiendo `markitdown`) o
correr Python vía WASM (Pyodide) en el navegador — no recomendado: las
dependencias de PDF/DOCX de markitdown no son compatibles con WASM y la
carga inicial sería de decenas de MB.

## Arquitectura del código

```
core/
  exceptions.py       # Jerarquía de errores del pipeline
  converter.py         # MarkitdownConverter: motor + fallbacks + validaciones
  optimizer.py          # Limpieza de Markdown (reduce tokens sin perder semántica)
  token_counter.py       # Conteo de tokens (tiktoken, con fallback sin red)
  pipeline.py             # Une converter -> optimizer -> métricas para 1 archivo
  batch_processor.py       # Paraleliza pipeline.py sobre N archivos
api/
  app.py                    # FastAPI: /convert, /convert-batch, /health
cli.py                       # Uso local / scripts
requirements.txt
```

Principio de diseño: cada módulo tiene una sola responsabilidad y no
conoce a los demás más allá de su input/output. `batch_processor` nunca
lanza excepciones por un archivo individual — cada `DocumentResult` lleva
su propio éxito/error, así un PDF corrupto en un lote de 50 no tumba el
resto.

## Manejo de errores

| Excepción | Cuándo ocurre |
|---|---|
| `UnsupportedFormatError` | Extensión distinta de `.pdf`/`.docx` |
| `CorruptFileError` | Archivo vacío, ilegible, o markitdown + fallback fallan ambos |
| `FileLockedError` | Archivo abierto/bloqueado por otro proceso (típico en Windows con Office abierto) |
| `EmptyContentError` | Conversión exitosa pero sin texto (ej. PDF escaneado sin OCR) |

## Ahorro de tokens: cómo se calcula

Se compara el Markdown **crudo** de markitdown vs el Markdown
**optimizado** (tras `optimizer.py`: dedupe de headers/footers repetidos,
colapso de whitespace, limpieza de links/imágenes vacíos). El conteo usa
`tiktoken` (`cl100k_base`) como estándar de referencia; si no hay red
disponible para descargar la tabla BPE (común en cold starts de free
tiers), cae automáticamente a una aproximación por caracteres — la
conversión nunca falla por esto.

## Uso local

```bash
pip install -r requirements.txt

# Un archivo
python cli.py informe.pdf -o salida/

# Lote (carpeta completa)
python cli.py ./mis_documentos/ -o salida/ --json
```

## Backend HTTP

```bash
uvicorn api.app:app --reload
# POST /convert       (multipart, campo "file")       -> descarga .md + header X-Token-Report
# POST /convert-batch  (multipart, campo "files" x N)   -> descarga .zip con .md + reporte.json
```

Para desplegar en Render/Railway/Fly.io: `uvicorn api.app:app --host 0.0.0.0 --port $PORT`.
La var de entorno `ALLOWED_ORIGIN` controla el CORS (ver `api/app.py`);
setearla al dominio real de Netlify en producción, no dejar `"*"`.

## Despliegue del backend en Render (paso a paso)

Se probó localmente todo el flujo (`/health`, `/convert`, `/convert-batch`,
y manejo de errores con archivos corruptos) antes de escribir esta guía.

1. **Subir el proyecto a un repo de GitHub** (público o privado, ambos
   sirven en el free tier de Render).
2. En [render.com](https://render.com), crear cuenta (no pide tarjeta) y
   elegir **New +** → **Blueprint**.
3. Conectar el repo. Render detecta `render.yaml` automáticamente y
   propone el servicio `md-converter-api` ya configurado (build command,
   start command, healthcheck).
4. Confirmar el deploy. El primer build tarda unos minutos (instala
   `markitdown` y sus dependencias). Render entrega una URL pública tipo
   `https://md-converter-api.onrender.com`.
5. **Actualizar el frontend**: en `netlify_frontend/index.html`, cambiar
   `API_BASE_URL` por esa URL.
6. **Actualizar CORS**: en el dashboard de Render → *Environment*,
   cambiar `ALLOWED_ORIGIN` de `"*"` al dominio real de Netlify (ej.
   `https://tu-app.netlify.app`) una vez que lo tengas.

**Limitaciones del free tier de Render a tener en cuenta** (verificadas
en julio 2026): el servicio se "duerme" tras 15 minutos sin tráfico, y el
primer request después tarda 30-60s en responder — vale la pena avisarlo
en el frontend si la primera conversión del día tarda. La instancia
gratuita tiene 512MB RAM / 0.1 CPU: alcanza de sobra para extracción de
texto, pero si más adelante se agrega OCR para PDFs escaneados va a hacer
falta subir de plan.

## Optimización recomendada para cold start (free tiers)

En el build del backend, precachear tiktoken para no depender de red en
runtime (ya incluido en `render.yaml`):
```bash
python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"
```

