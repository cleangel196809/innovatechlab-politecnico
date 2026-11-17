# -*- coding: utf-8 -*-
"""Material del curso cargado por el docente (opcional) para que el agente lo use como fuente.

Lee texto de: Word (.docx), PowerPoint (.pptx), Excel (.xlsx/.xlsm), PDF, OpenDocument (.odt/.odp/.ods),
texto plano (.txt, .md, .csv, .json, .html, .xml, .gift, código fuente…) y comprimidos (.zip, recorridos de
forma segura). Imágenes, audio y video no tienen texto: se registran por nombre y se adjuntan al curso.

Además detecta a qué núcleo pertenece cada archivo por su nombre o carpeta («N2», «Núcleo 2», «nucleo_2»,
«Unidad 2», «U2», «Semana…» no cuenta) para entregárselo al agente en el núcleo correcto.
"""
import io
import os
import re
import zipfile
from xml.etree import ElementTree

MAX_FILE_MB = 30          # por archivo
MAX_TOTAL_MB = 60         # por carga completa
MAX_ZIP_FILES = 200
MAX_ZIP_UNCOMPRESSED = 300 * 1024 * 1024
MAX_TEXT = 120000         # caracteres que se guardan por archivo

TEXT_EXT = (".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".html", ".htm", ".gift", ".java", ".py", ".js", ".ts",
            ".sql", ".yaml", ".yml", ".properties", ".css", ".c", ".cpp", ".cs", ".kt", ".php", ".rb", ".go", ".sh",
            ".ipynb", ".rtf")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp")
MEDIA_EXT = (".mp4", ".webm", ".mov", ".mp3", ".wav", ".m4a", ".ogg")

KIND_LABELS = {"documento": "Documento", "presentacion": "Presentación", "hoja": "Hoja de cálculo", "pdf": "PDF",
               "texto": "Texto", "imagen": "Imagen", "multimedia": "Audio/video", "otro": "Otro"}


def kind_of(name):
    n = name.lower()
    if n.endswith((".docx", ".doc", ".odt")):
        return "documento"
    if n.endswith((".pptx", ".ppt", ".odp")):
        return "presentacion"
    if n.endswith((".xlsx", ".xlsm", ".xls", ".ods", ".csv")):
        return "hoja"
    if n.endswith(".pdf"):
        return "pdf"
    if n.endswith(IMAGE_EXT):
        return "imagen"
    if n.endswith(MEDIA_EXT):
        return "multimedia"
    if n.endswith(TEXT_EXT):
        return "texto"
    return "otro"


def section_number(name):
    """Número de núcleo de una sección («Núcleo 2 – …», «Núcleo IA 2 …»); None si no es un núcleo."""
    m = re.match(r"(?i)\s*n[úu]cleo\b\D{0,15}?(\d{1,2})", name or "")
    return int(m.group(1)) if m else None


def _fix_zip_name(info):
    """Los .zip creados sin la bandera UTF-8 llegan en cp437 («N├║cleo»): se recupera el nombre real."""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


def detect_nucleo(path, text=""):
    """Número de núcleo según el nombre/carpeta del archivo (0 = material general)."""
    s = path.replace("\\", "/")
    pats = [r"(?i)n[úu]cleo[\s_\-\.]*(\d{1,2})", r"(?i)(?:^|[/\s_\-\.(])n(\d{1,2})(?=$|[/\s_\-\.)])",
            r"(?i)unidad[\s_\-\.]*(\d{1,2})", r"(?i)(?:^|[/\s_\-\.(])u(\d{1,2})(?=$|[/\s_\-\.)])",
            r"(?i)m[óo]dulo[\s_\-\.]*(\d{1,2})"]
    for p in pats:
        m = re.search(p, s)
        if m:
            return int(m.group(1))
    head = (text or "")[:400]
    m = re.search(r"(?i)\bn[úu]cleo\s+(\d{1,2})\b", head)
    return int(m.group(1)) if m else 0


def _xml_text(data, tag_ns):
    root = ElementTree.fromstring(data)
    out, cur = [], []
    for el in root.iter():
        if el.tag == tag_ns + "t" and el.text:
            cur.append(el.text)
        elif el.tag == tag_ns + "p":
            if cur:
                out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return "\n".join(x for x in out if x.strip())


def _docx(raw):
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        root = ElementTree.fromstring(z.read("word/document.xml"))
    lines = []
    body = root.find(W + "body")
    for block in (body if body is not None else root):
        if block.tag == W + "tbl":
            for tr in block.iter(W + "tr"):
                cells = ["".join(t.text or "" for t in tc.iter(W + "t")).strip() for tc in tr.iter(W + "tc")]
                if any(cells):
                    lines.append(" | ".join(cells))
        else:
            t = "".join(n.text or "" for n in block.iter(W + "t")).strip()
            if t:
                lines.append(t)
    return "\n".join(lines)


def _pptx(raw):
    A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    out = []
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = sorted([n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)],
                       key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)))
        for i, n in enumerate(names, 1):
            txt = _xml_text(z.read(n), A)
            notes = "ppt/notesSlides/notesSlide%d.xml" % i
            nt = _xml_text(z.read(notes), A) if notes in z.namelist() else ""
            out.append("[Diapositiva %d]\n%s%s" % (i, txt, ("\nNotas: " + nt) if nt.strip() else ""))
    return "\n\n".join(out)


def _xlsx(raw):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets[:10]:
        out.append("[Hoja %s]" % ws.title)
        for k, row in enumerate(ws.iter_rows(values_only=True)):
            if k >= 400:
                out.append("…")
                break
            vals = ["" if v is None else str(v) for v in row]
            if any(v.strip() for v in vals):
                out.append(" | ".join(vals).rstrip(" |"))
    wb.close()
    return "\n".join(out)


def _odf(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        data = z.read("content.xml")
    root = ElementTree.fromstring(data)
    T = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
    return "\n".join("".join(el.itertext()).strip() for el in root.iter() if el.tag in (T + "p", T + "h")
                     and "".join(el.itertext()).strip())


def _pdf(raw):
    try:
        from odoo.tools.pdf import PdfFileReader
    except ImportError:  # fuera de Odoo (pruebas)
        from pypdf import PdfReader as PdfFileReader  # noqa: N813
    reader = PdfFileReader(io.BytesIO(raw), strict=False)
    try:
        pages = [reader.getPage(i) for i in range(reader.getNumPages())]
        return "\n".join((p.extractText() or "") for p in pages[:150])
    except AttributeError:
        return "\n".join((p.extract_text() or "") for p in reader.pages[:150])


def _plain(raw, name):
    for enc in ("utf-8-sig", "latin-1"):
        try:
            txt = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if name.lower().endswith((".html", ".htm", ".xml")):
        txt = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", txt)
        txt = re.sub(r"<[^>]+>", " ", txt)
    if name.lower().endswith(".ipynb"):
        try:
            import json
            nb = json.loads(txt)
            txt = "\n\n".join("".join(c.get("source") or []) for c in nb.get("cells") or [])
        except ValueError:
            pass
    return txt


def extract(raw, name):
    """Texto de un archivo (o '' si no tiene texto legible). No lanza excepciones."""
    n = name.lower()
    try:
        if n.endswith(".docx"):
            return _docx(raw)
        if n.endswith(".pptx"):
            return _pptx(raw)
        if n.endswith((".xlsx", ".xlsm")):
            return _xlsx(raw)
        if n.endswith((".odt", ".odp", ".ods")):
            return _odf(raw)
        if n.endswith(".pdf"):
            return _pdf(raw)
        if n.endswith(TEXT_EXT):
            return _plain(raw, name)
    except Exception as e:  # noqa: BLE001
        return "[No se pudo leer %s: %s]" % (name, str(e)[:120])
    return ""


def unpack(raw, name):
    """Lista de (ruta, bytes) del archivo; los .zip se recorren con límites contra bombas de compresión."""
    if not name.lower().endswith(".zip"):
        return [(name, raw)]
    out, total = [], 0
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for info in z.infolist():
                if info.is_dir() or len(out) >= MAX_ZIP_FILES:
                    continue
                fname = _fix_zip_name(info)
                base = os.path.basename(fname)
                if not base or base.startswith((".", "~$")) or "__MACOSX" in fname:
                    continue
                total += info.file_size
                if info.file_size > MAX_FILE_MB * 1024 * 1024 or total > MAX_ZIP_UNCOMPRESSED:
                    out.append((fname, None))  # demasiado grande: se registra sin contenido
                    continue
                data = z.read(info)
                if base.lower().endswith(".zip"):
                    out += [("%s/%s" % (os.path.dirname(fname), p), d)
                            for p, d in unpack(data, base)[:MAX_ZIP_FILES]]
                else:
                    out.append((fname, data))
    except zipfile.BadZipFile:
        return [(name, raw)]
    return out


def summarize(items, limit=4000):
    """Texto breve con los archivos recibidos (para la bitácora)."""
    return "; ".join("%s (%s%s)" % (os.path.basename(i["name"]), KIND_LABELS.get(i["kind"], i["kind"]),
                                    ", núcleo %s" % i["nucleo"] if i["nucleo"] else "") for i in items)[:limit]
