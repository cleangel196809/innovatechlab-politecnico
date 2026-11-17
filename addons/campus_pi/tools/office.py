# -*- coding: utf-8 -*-
"""Documentos institucionales del Politécnico Internacional generados por el agente.

* Presentación PPTX 16:9 con el estilo del video modelo (barra azul con logo, tarjetas con borde
  celeste, ilustraciones, bloques de código oscuros, pie con programa y avance) y la narración en las
  notas del orador.
* Paquete DOCX del núcleo con los formatos de la Unidad Virtual: Recursos bibliográficos, Lectura,
  Guion del video, Actividad formativa (H5P), Infografía y Caso integrador con rúbrica.

Requiere python-pptx y python-docx (se instalan en el Dockerfile). Las importaciones son perezosas
para que el módulo cargue aunque falten.
"""
import io
import os
import re

from lxml import html as lxml_html

from . import deck as deck_tools
from . import visual

IMG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "src", "img")
LOGO_COLOR = os.path.join(IMG_DIR, "logo_pi_color.png")
LOGO_WHITE = os.path.join(IMG_DIR, "logo_pi_blanco.png")

NAVY = "0B1F5B"
NAVY_DOC = "002060"
SKY = "1E9BD7"
INK = "1F2937"
HEAD = "1F3A5F"
MUTED = "595959"
CODE_BG = "0F1B2D"
CODE_FILL = "F2F4F7"
CALLOUT = "EAF3FB"
PAGE_BG = "F4F8FC"


def _rgb(h):
    from pptx.dml.color import RGBColor
    return RGBColor.from_string(h)


# ======================================================================== PPTX
def build_pptx(slides, meta):
    """slides: lista normalizada (deck.normalize). meta: course, section, program, teacher."""
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.util import Emu, Inches, Pt

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    blank = prs.slide_layouts[6]
    total = len(slides)
    course = meta.get("course") or ""
    section = meta.get("section") or ""
    program = meta.get("program") or "Politécnico Internacional"
    nuc_label = meta.get("nucleo_label") or ""

    def box(sl, x, y, w, h, fill, line=None, shape=MSO_SHAPE.RECTANGLE):
        s = sl.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
        s.fill.solid()
        s.fill.fore_color.rgb = _rgb(fill)
        if line:
            s.line.color.rgb = _rgb(line)
            s.line.width = Pt(0.75)
        else:
            s.line.fill.background()
        s.shadow.inherit = False
        return s

    def text(sl, x, y, w, h, txt, size=18, color=INK, bold=False, align=PP_ALIGN.LEFT, font="Calibri",
             anchor=MSO_ANCHOR.TOP, italic=False):
        tb = sl.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        tf.margin_left = tf.margin_right = Inches(0.05)
        lines = txt if isinstance(txt, list) else [txt]
        for i, ln in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align
            r = p.add_run()
            r.text = ln
            r.font.size = Pt(size)
            r.font.bold = bold
            r.font.italic = italic
            r.font.name = font
            r.font.color.rgb = _rgb(color)
        return tb

    def chrome(sl, n):
        box(sl, 0, 0, 13.333, 7.5, PAGE_BG)
        box(sl, 0, 0, 13.333, 0.62, NAVY)
        if os.path.exists(LOGO_WHITE):
            sl.shapes.add_picture(LOGO_WHITE, Inches(0.3), Inches(0.08), height=Inches(0.46))
        tb = sl.shapes.add_textbox(Inches(5.5), Inches(0.05), Inches(7.55), Inches(0.55))
        tf = tb.text_frame
        tf.margin_right = Inches(0.05)
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.RIGHT
        r = p.add_run()
        r.text = course + (" · " if nuc_label else "")
        r.font.size, r.font.color.rgb, r.font.name = Pt(12), _rgb("FFFFFF"), "Calibri"
        if nuc_label:
            r2 = p.add_run()
            r2.text = nuc_label
            r2.font.size, r2.font.bold, r2.font.color.rgb, r2.font.name = Pt(12), True, _rgb("8FD3F4"), "Calibri"
        p2 = tf.add_paragraph()
        p2.alignment = PP_ALIGN.RIGHT
        r3 = p2.add_run()
        r3.text = section[:90]
        r3.font.size, r3.font.color.rgb, r3.font.name = Pt(11), _rgb("FFFFFF"), "Calibri"
        box(sl, 0, 7.12, 13.333, 0.01, "DCE3F0")
        box(sl, 0, 7.1, 13.333 * (n + 1) / float(total), 0.05, SKY)
        text(sl, 0.4, 7.17, 9, 0.3, "%s · %s" % ("Politécnico Internacional", program)[:120], 9, MUTED)
        text(sl, 11.8, 7.17, 1.15, 0.3, "%d / %d" % (n + 1, total), 9, MUTED, align=PP_ALIGN.RIGHT)

    def card(sl, x, y, w, h, txt, size=17):
        box(sl, x, y, w, h, "FFFFFF", line="E3E9F2")
        box(sl, x, y, 0.07, h, SKY)
        text(sl, x + 0.22, y, w - 0.32, h, txt, size, INK, anchor=MSO_ANCHOR.MIDDLE)

    def cards(sl, pts, x, y, w, bottom=6.85):
        if not pts:
            return
        gap = 0.18
        h = min(0.95, max(0.62, (bottom - y - gap * (len(pts) - 1)) / len(pts)))
        size = 17 if max(len(p) for p in pts) < 70 else 15
        for i, p in enumerate(pts):
            card(sl, x, y + i * (h + gap), w, h, p, size)

    def illustration(sl, s, x, y, w):
        try:
            png = visual.illustration_png(s.get("icon"), s.get("icon_label") or "", 900)
            sl.shapes.add_picture(io.BytesIO(png), Inches(x), Inches(y), width=Inches(w))
        except Exception:  # noqa: BLE001
            pass

    def code_block(sl, code, x, y, w, h):
        box(sl, x, y, w, h, CODE_BG, shape=MSO_SHAPE.ROUNDED_RECTANGLE).adjustments[0] = 0.03
        lines = code.split("\n")[:24]
        longest = max((len(l) for l in lines), default=0)
        size = 15 if len(lines) <= 12 and longest < 60 else (13 if len(lines) <= 16 and longest < 85 else 11)
        tb = text(sl, x + 0.3, y + 0.25, w - 0.5, h - 0.4, lines, size, "E6EDF7", font="Consolas",
                  anchor=MSO_ANCHOR.MIDDLE)
        return tb

    for n, s in enumerate(slides):
        sl = prs.slides.add_slide(blank)
        lay = s.get("layout")
        if lay == "portada":
            box(sl, 0, 0, 13.333, 7.5, NAVY)
            box(sl, 0.9, 4.25, 8.5, 0.05, SKY)
            if os.path.exists(LOGO_WHITE):
                sl.shapes.add_picture(LOGO_WHITE, Inches(10.6), Inches(4.9), height=Inches(1.9))
            text(sl, 0.9, 1.55, 11, 0.5, (nuc_label or "").upper(), 16, "8FD3F4", True)
            text(sl, 0.9, 2.05, 11.2, 2.1, s["title"], 40, "FFFFFF", True, anchor=MSO_ANCHOR.BOTTOM)
            sub = s.get("subtitle") or section
            text(sl, 0.9, 4.45, 9.3, 0.6, sub, 20, "FFFFFF", italic=True)
            text(sl, 0.9, 5.1, 9.3, 1.2, [course, meta.get("teacher") or ""], 16, "D6E4F5")
            if s.get("points"):
                text(sl, 0.9, 6.2, 9.3, 0.8, "Meta: " + s["points"][0], 13, "D6E4F5")
        else:
            chrome(sl, n)
            text(sl, 0.5, 0.85, 12.3, 0.75, s["title"], 30, "0B1F5B", True)
            top = 1.75
            if s.get("subtitle"):
                text(sl, 0.5, 1.5, 12.3, 0.45, s["subtitle"], 16, "3A4A68", italic=True)
                top = 2.05
            pts = s.get("points") or []
            if lay == "codigo":
                if pts:
                    cards(sl, pts[:4], 0.5, top, 4.6)
                    code_block(sl, s["code"], 5.4, top, 7.45, 6.85 - top)
                else:
                    code_block(sl, s["code"], 0.5, top, 12.35, 6.85 - top)
            elif lay == "tabla":
                hd, rows = s["table"]["headers"], s["table"]["rows"]
                tb = sl.shapes.add_table(len(rows) + 1, len(hd), Inches(0.5), Inches(top), Inches(12.35),
                                         Inches(0.5 * (len(rows) + 1))).table
                for j, h in enumerate(hd):
                    c = tb.cell(0, j)
                    c.text = h
                    c.fill.solid()
                    c.fill.fore_color.rgb = _rgb(NAVY_DOC)
                    for p in c.text_frame.paragraphs:
                        for r in p.runs:
                            r.font.bold, r.font.size, r.font.color.rgb = True, Pt(15), _rgb("FFFFFF")
                for i, row in enumerate(rows):
                    for j in range(len(hd)):
                        c = tb.cell(i + 1, j)
                        c.text = row[j] if j < len(row) else ""
                        c.fill.solid()
                        c.fill.fore_color.rgb = _rgb("FFFFFF" if i % 2 == 0 else "EEF4FB")
                        for p in c.text_frame.paragraphs:
                            for r in p.runs:
                                r.font.size, r.font.color.rgb = Pt(14), _rgb(INK)
            elif lay == "proceso" and pts:
                k = len(pts[:6])
                w = (12.35 - 0.3 * (k - 1)) / k
                for i, p in enumerate(pts[:6]):
                    x = 0.5 + i * (w + 0.3)
                    c = box(sl, x + w / 2 - 0.45, top + 0.4, 0.9, 0.9, NAVY if i % 2 == 0 else SKY, shape=MSO_SHAPE.OVAL)
                    c.text_frame.text = str(i + 1)
                    for pp in c.text_frame.paragraphs:
                        pp.alignment = PP_ALIGN.CENTER
                        for r in pp.runs:
                            r.font.size, r.font.bold, r.font.color.rgb = Pt(24), True, _rgb("FFFFFF")
                    if i < k - 1:
                        a = box(sl, x + w / 2 + 0.55, top + 0.75, w - 0.8, 0.2, "C9D6E8", shape=MSO_SHAPE.RIGHT_ARROW)
                        a.rotation = 0
                    ch = min(2.6, 6.85 - top - 1.6)
                    box(sl, x, top + 1.6, w, ch, "FFFFFF", line="E3E9F2")
                    box(sl, x, top + 1.6, w, 0.07, SKY)
                    text(sl, x + 0.15, top + 1.8, w - 0.3, ch - 0.3, p, 16 if len(p) < 60 else 14, INK)
            elif lay == "comparacion" and pts:
                half = (len(pts) + 1) // 2
                for col, group in enumerate((pts[:half], pts[half:])):
                    cards(sl, group, 0.5 + col * 6.3, top, 6.05)
            elif lay == "cita":
                box(sl, 1.2, top + 0.4, 10.9, 3.6, "FFFFFF", line="E3E9F2")
                box(sl, 1.2, top + 0.4, 0.1, 3.6, SKY)
                text(sl, 1.6, top + 0.6, 10.2, 3.2, (pts[0] if pts else s.get("subtitle") or ""), 26, "0B1F5B",
                     italic=True, anchor=MSO_ANCHOR.MIDDLE)
                if len(pts) > 1:
                    text(sl, 1.6, top + 4.2, 10.2, 1.2, pts[1:3], 16, "3A4A68")
            else:  # puntos / cierre / respaldo
                cards(sl, pts, 0.5, top + 0.15, 7.45)
                illustration(sl, s, 8.25, top + 0.55, 4.6)
        notes = deck_tools.narration(s, n, total)
        if notes:
            sl.notes_slide.notes_text_frame.text = notes
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# ======================================================================== DOCX
def _docx():
    import docx  # noqa: F401
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor
    return locals()


def _shade(cell, fill):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def _borders(table, color="BFC8D6", size=4):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    tbl = table._tbl
    tblPr = tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement("w:%s" % edge)
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), str(size))
        e.set(qn("w:color"), color)
        b.append(e)
    tblPr.append(b)


def _run(p, txt, bold=False, italic=False, size=None, color=None, font=None):
    from docx.shared import Pt, RGBColor
    r = p.add_run(txt)
    r.bold, r.italic = bold, italic
    if size:
        r.font.size = Pt(size)
    if color:
        r.font.color.rgb = RGBColor.from_string(color)
    if font:
        r.font.name = font
        rpr = r._element.get_or_add_rPr()
        from docx.oxml.ns import qn
        rf = rpr.find(qn("w:rFonts"))
        if rf is not None:
            rf.set(qn("w:eastAsia"), font)
    return r


def _cell_text(cell, txt, bold=False, color=INK, size=10, align=None, italic=False):
    cell.text = ""
    p = cell.paragraphs[0]
    if align is not None:
        p.alignment = align
    lines = txt if isinstance(txt, list) else [txt]
    for i, ln in enumerate(lines):
        if i:
            p = cell.add_paragraph()
            if align is not None:
                p.alignment = align
        _run(p, str(ln or ""), bold=bold, color=color, size=size, italic=italic)
    return cell


def _new_doc(landscape=False):
    d = _docx()
    doc = d["Document"]()
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = d["Pt"](11)
    st.font.color.rgb = d["RGBColor"].from_string(INK)
    sec = doc.sections[0]
    if landscape:
        sec.orientation = d["WD_ORIENT"].LANDSCAPE
        sec.page_width, sec.page_height = d["Inches"](11), d["Inches"](8.5)
    else:
        sec.page_width, sec.page_height = d["Inches"](8.5), d["Inches"](11)
    for m in ("left_margin", "right_margin"):
        setattr(sec, m, d["Inches"](0.9))
    sec.top_margin, sec.bottom_margin = d["Inches"](0.8), d["Inches"](0.8)
    return doc, d


def _format_header(doc, d, formato):
    """Encabezado de los formatos de la Unidad Virtual (logo, nombre del formato, versión y fecha)."""
    hdr = doc.sections[0].header
    hdr.is_linked_to_previous = False
    t = hdr.add_table(3, 3, width=doc.sections[0].page_width - doc.sections[0].left_margin - doc.sections[0].right_margin)
    _borders(t, "000000", 4)
    t.alignment = d["WD_TABLE_ALIGNMENT"].CENTER
    a = t.cell(0, 0).merge(t.cell(2, 0))
    a.text = ""
    if os.path.exists(LOGO_COLOR):
        a.paragraphs[0].alignment = d["WD_ALIGN_PARAGRAPH"].CENTER
        a.paragraphs[0].add_run().add_picture(LOGO_COLOR, height=d["Inches"](0.75))
    top = t.cell(0, 1).merge(t.cell(0, 2))
    C = d["WD_ALIGN_PARAGRAPH"].CENTER
    _cell_text(top, "POLITÉCNICO INTERNACIONAL", True, "2F4B9A", 12, C)
    _cell_text(t.cell(1, 1), "UNIDAD VIRTUAL", True, "2F4B9A", 11, C)
    _cell_text(t.cell(1, 2), "Versión: 1.0", True, "2F4B9A", 10, C)
    _cell_text(t.cell(2, 1), "FORMATO “%s”" % formato, True, "2F4B9A", 11, C)
    _cell_text(t.cell(2, 2), ["Fecha:", "31/03/2022"], True, "2F4B9A", 10, C)
    widths = [1.4, 4.6, 1.3]
    for row in t.rows:
        for j, c in enumerate(row.cells):
            c.width = d["Inches"](widths[j])


def _footer_note(doc, d, text_):
    f = doc.sections[0].footer
    p = f.paragraphs[0]
    p.alignment = d["WD_ALIGN_PARAGRAPH"].CENTER
    _run(p, text_, size=7, color="000000")


def _heading(doc, txt, level=1):
    p = doc.add_paragraph()
    size = {0: 22, 1: 16, 2: 13, 3: 12}.get(level, 12)
    color = NAVY_DOC if level <= 1 else HEAD
    _run(p, txt, bold=True, size=size, color=color)
    p.paragraph_format.space_before = __import__("docx").shared.Pt(14 if level <= 1 else 10)
    p.paragraph_format.space_after = __import__("docx").shared.Pt(4)
    p.paragraph_format.keep_with_next = True
    return p


def _para(doc, txt, size=11, color=INK, italic=False, bold=False, align=None):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    _run(p, txt, bold=bold, italic=italic, size=size, color=color)
    return p


def _bullets(doc, items, numbered=False):
    for it in items:
        try:
            p = doc.add_paragraph(style="List Number" if numbered else "List Bullet")
        except KeyError:
            p = doc.add_paragraph()
            _run(p, "• ")
        _run(p, str(it))


def _code(doc, code, caption=None):
    t = doc.add_table(1, 1)
    c = t.cell(0, 0)
    _shade(c, CODE_FILL)
    c.text = ""
    lines = str(code).split("\n")
    p = c.paragraphs[0]
    for i, ln in enumerate(lines):
        if i:
            p = c.add_paragraph()
        p.paragraph_format.space_after = __import__("docx").shared.Pt(0)
        _run(p, ln or " ", size=9, font="Courier New", color="1F2937")
    if caption:
        _para(doc, caption, 9, MUTED, italic=True)


def _callout(doc, title, body_lines):
    t = doc.add_table(1, 1)
    c = t.cell(0, 0)
    _shade(c, CALLOUT)
    c.text = ""
    _run(c.paragraphs[0], title, bold=True, color=HEAD)
    for ln in body_lines:
        p = c.add_paragraph()
        _run(p, ln)
    doc.add_paragraph()


def _data_table(doc, headers, rows, widths=None, header_fill=NAVY_DOC, size=10):
    d = _docx()
    t = doc.add_table(len(rows) + 1, len(headers))
    _borders(t)
    for j, h in enumerate(headers):
        c = t.cell(0, j)
        _shade(c, header_fill)
        _cell_text(c, h, True, "FFFFFF", size)
    for i, r in enumerate(rows):
        for j in range(len(headers)):
            _cell_text(t.cell(i + 1, j), r[j] if j < len(r) else "", size=size)
    if widths:
        for row in t.rows:
            for j, c in enumerate(row.cells):
                c.width = d["Inches"](widths[j])
    doc.add_paragraph()
    return t


def _html_into(doc, html_text):
    """Convierte el HTML de las lecturas (h3-h5, p, ul/ol, table, pre, div.cp-callout) a Word."""
    if not html_text or not str(html_text).strip():
        return
    try:
        root = lxml_html.fragment_fromstring(str(html_text), create_parent="div")
    except Exception:  # noqa: BLE001
        _para(doc, re.sub(r"<[^>]+>", " ", str(html_text)))
        return

    def inline(p, el):
        if el.text:
            _run(p, el.text)
        for ch in el:
            tag = ch.tag if isinstance(ch.tag, str) else ""
            t = ch.text_content()
            if tag in ("b", "strong"):
                _run(p, t, bold=True)
            elif tag in ("i", "em"):
                _run(p, t, italic=True)
            elif tag == "code":
                _run(p, t, font="Courier New", size=10)
            elif tag == "a":
                href = ch.get("href") or ""
                _run(p, t, color="1F5FBF")
                if href and href not in t:
                    _run(p, " (%s)" % href, size=9, color=MUTED)
            elif tag == "br":
                _run(p, "\n")
            else:
                _run(p, t)
            if ch.tail:
                _run(p, ch.tail)

    for el in root:
        tag = el.tag if isinstance(el.tag, str) else ""
        cls = el.get("class") or ""
        if tag in ("h1", "h2", "h3"):
            _heading(doc, el.text_content().strip(), 1)
        elif tag in ("h4", "h5", "h6"):
            _heading(doc, el.text_content().strip(), 2 if tag == "h4" else 3)
        elif tag == "p":
            p = doc.add_paragraph()
            if "caption" in cls or "cp-small" in cls:
                _run(p, el.text_content().strip(), italic=True, size=9, color=MUTED)
            else:
                inline(p, el)
        elif tag in ("ul", "ol"):
            for li in el.iter("li"):
                try:
                    p = doc.add_paragraph(style="List Number" if tag == "ol" else "List Bullet")
                except KeyError:
                    p = doc.add_paragraph()
                inline(p, li)
        elif tag == "pre":
            _code(doc, el.text_content().strip("\n"))
        elif tag == "table":
            rows = [[re.sub(r"\s+", " ", c.text_content()).strip() for c in tr.xpath("./th|./td")] for tr in el.iter("tr")]
            rows = [r for r in rows if r]
            if rows:
                ncol = max(len(r) for r in rows)
                _data_table(doc, rows[0] + [""] * (ncol - len(rows[0])), [r + [""] * (ncol - len(r)) for r in rows[1:]])
        elif tag in ("div", "blockquote", "aside") and ("callout" in cls or tag != "div"):
            head = el.find(".//b")
            title = head.text_content().strip() if head is not None else ""
            body = re.sub(r"\s+", " ", el.text_content()).strip()
            if title and body.startswith(title):
                body = body[len(title):].strip()
            _callout(doc, title or "Nota", [body])
        elif tag == "div":
            _html_into(doc, lxml_html.tostring(el, encoding="unicode", method="html")[len("<div>"):-len("</div>")]
                       if not cls else lxml_html.tostring(el, encoding="unicode"))
        else:
            txt = el.text_content().strip()
            if txt:
                _para(doc, txt)


def _save(doc):
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- lectura
def docx_lectura(kit, meta):
    doc, d = _new_doc()
    lec = kit.get("lectura") or {}
    # Portada azul institucional
    t = doc.add_table(1, 1)
    c = t.cell(0, 0)
    _shade(c, NAVY_DOC)
    t.rows[0].height = d["Inches"](8.6)
    c.text = ""
    p = c.paragraphs[0]
    for _ in range(7):
        c.add_paragraph()
    p = c.add_paragraph()
    _run(p, (meta.get("nucleo_label") or "").upper(), size=12, color="FFFFFF")
    p = c.add_paragraph()
    _run(p, lec.get("titulo") or meta.get("section") or "", bold=True, size=26, color="FFFFFF")
    p = c.add_paragraph()
    _run(p, "━" * 40, color="1E9BD7", size=12)
    p = c.add_paragraph()
    _run(p, "Lectura del %s" % (meta.get("nucleo_label") or "núcleo"), italic=True, size=13, color="FFFFFF")
    p = c.add_paragraph()
    _run(p, meta.get("course") or "", size=13, color="FFFFFF")
    p = c.add_paragraph()
    _run(p, meta.get("teacher") or "", size=11, color="FFFFFF")
    for _ in range(4):
        c.add_paragraph()
    if os.path.exists(LOGO_WHITE):
        p = c.add_paragraph()
        p.alignment = d["WD_ALIGN_PARAGRAPH"].RIGHT
        p.add_run().add_picture(LOGO_WHITE, height=d["Inches"](1.6))
    doc.add_paragraph().add_run().add_break(d["WD_BREAK"].PAGE)
    doc.sections[0].different_first_page_header_footer = True  # la portada va sin encabezado
    hp = doc.sections[0].header.paragraphs[0]
    _run(hp, "%s · %s" % ((meta.get("nucleo_label") or "").upper(), lec.get("titulo") or ""), size=9, color=MUTED)
    if lec.get("presentacion"):
        _heading(doc, "Presentación", 1)
        for par in re.split(r"\n\s*\n", lec["presentacion"]):
            _para(doc, par.strip())
    if lec.get("logros"):
        _callout(doc, "Lo que lograrás en este núcleo", ["• " + x for x in lec["logros"]])
    _html_into(doc, lec.get("secciones_html") or lec.get("html") or "")
    if lec.get("buenas_practicas"):
        _heading(doc, "Buenas prácticas para recordar", 1)
        _bullets(doc, lec["buenas_practicas"])
    if lec.get("casos"):
        _heading(doc, "Casos para reflexionar", 1)
        for i, cs in enumerate(lec["casos"], 1):
            _para(doc, "Caso %d. %s" % (i, cs.get("titulo") or ""), bold=True, color=HEAD)
            _para(doc, cs.get("texto") or "")
    if lec.get("glosario"):
        _heading(doc, "Glosario", 1)
        _data_table(doc, ["Término", "Significado"], [[g.get("termino", ""), g.get("significado", "")] for g in lec["glosario"]],
                    [1.9, 4.8])
    if lec.get("referencias"):
        _heading(doc, "Referencias", 1)
        for r in lec["referencias"]:
            p = _para(doc, r, 10)
            p.paragraph_format.left_indent = d["Inches"](0.4)
            p.paragraph_format.first_line_indent = d["Inches"](-0.4)
    return _save(doc)


# ------------------------------------------------------------- bibliografía
def docx_bibliografia(kit, meta):
    doc, d = _new_doc(landscape=True)
    _format_header(doc, d, "BIBLIOGRAFÍA Y MATERIAL DE APOYO")
    bib = kit.get("bibliografia") or {}
    nuc = str(meta.get("nucleo_num") or "")
    _para(doc, "CONTENIDOS TEMÁTICOS PRINCIPALES", bold=True)
    _para(doc, "La asignatura deberá tener por lo menos un libro guía de la base de datos (ver recomendaciones) en los cuales "
               "el estudiante pueda consultar información de todos los contenidos temáticos del curso:", 10)
    rows = []
    for b in bib.get("principal") or []:
        name = b.get("titulo") or ""
        if b.get("referencia"):
            name += "\n\nReferencia: " + b["referencia"]
        rows.append([nuc, name, b.get("autor") or "", b.get("url") or "", b.get("tema") or "", b.get("paginas") or ""])
    _data_table(doc, ["Núcleo/ Corte de aprendizaje", "Nombre del libro", "Autor", "Enlace web (base de datos)",
                      "Tema de consulta", "Detallar el número de páginas o capítulos que el estudiante debe consultar"],
                rows or [[nuc, "", "", "", "", ""]], [0.9, 2.3, 1.4, 1.9, 1.5, 1.5], header_fill="2F4B9A")
    _para(doc, "MATERIAL DE APOYO COMPLEMENTARIO", bold=True)
    _para(doc, "Incluir todos los documentos (artículos, e-books, capítulo de libro, presentaciones, enlaces a sitios web "
               "especializados, videos, audios, diagramas, imágenes, etc.) de sitios externos, que el estudiante puede consultar "
               "como material de apoyo adicional a los libros citados anteriormente.", 10)
    rows = []
    for b in bib.get("complementaria") or []:
        name = b.get("titulo") or ""
        if b.get("referencia"):
            name += "\n\nReferencia: " + b["referencia"]
        rows.append([nuc, name, b.get("autor") or "", b.get("url") or ""])
    _data_table(doc, ["Núcleo/ Corte de aprendizaje", "Nombre del documento", "Autor", "Enlace web"],
                rows or [[nuc, "", "", ""]], [0.9, 3.1, 1.6, 3.9], header_fill="2F4B9A")
    _para(doc, "Recomendaciones: el libro guía principal debe tomarse preferiblemente de las bases de datos institucionales "
               "(E-libro: https://elibro.net/es/lc/politecnicointernacional/inicio/).", 9, MUTED, italic=True)
    return _save(doc)


# ------------------------------------------------------------------- guion
def docx_guion(slides, meta):
    doc, d = _new_doc()
    starts, total_s = deck_tools.timeline(slides)
    p = _para(doc, "%s · %s · Politécnico Internacional I.E.S." % (meta.get("course") or "", meta.get("program") or ""), 10, MUTED)
    _para(doc, "Docente: %s · Duración aproximada: %s minutos · Narración con voz neuronal en español (%s)." % (
        meta.get("teacher") or "", ("%.1f" % (total_s / 60.0)).replace(".", ","), meta.get("voice") or "voz del campus"),
        10, MUTED)
    if meta.get("objective"):
        _para(doc, "Resultado de aprendizaje: %s" % meta["objective"], 10, MUTED)
    _heading(doc, "Guion del video explicativo · %s" % (meta.get("section") or ""), 0)
    for i, s in enumerate(slides):
        _heading(doc, "Escena %d. %s  (%s)" % (i + 1, s["title"], deck_tools.mmss(starts[i])), 1)
        _para(doc, deck_tools.narration(s, i, len(slides)))
        visual_txt = "; ".join(s.get("points") or [])
        if visual_txt or s.get("code"):
            _para(doc, "En pantalla: %s%s" % (visual_txt, " · bloque de código" if s.get("code") else ""), 9, MUTED, italic=True)
    return _save(doc)


# ---------------------------------------------------------------- actividad
def docx_actividad(act, slides, meta):
    doc, d = _new_doc()
    starts, _t = deck_tools.timeline(slides)
    qs = act.get("preguntas") or []

    def when(q):
        try:
            k = max(0, min(len(slides) - 1, int(q.get("escena") or 1) - 1))
        except (TypeError, ValueError):
            k = 0
        nxt = starts[k + 1] if k + 1 < len(starts) else _t
        return deck_tools.mmss(max(nxt - 3, 0))

    t = doc.add_table(6, 2)
    _borders(t)
    rows = [
        ("Asignatura", meta.get("course") or ""), ("Núcleo", meta.get("section") or ""),
        ("Nombre de la actividad", act.get("titulo") or "Actividad interactiva"),
        ("Tipo de actividad", "VideoQuiz (Interactive Video) en H5P con %d preguntas tipo caso, sobre el video explicativo del "
                              "núcleo (https://h5p.org/interactive-video). Cargar el video desde 00:00. Momentos: %s." % (
                                  len(qs), " · ".join("Pregunta %d: %s" % (i + 1, when(q)) for i, q in enumerate(qs)))),
        ("Objetivo", act.get("objetivo") or ""), ("Instrucción para el estudiante", act.get("instruccion") or ""),
    ]
    for i, (k, v) in enumerate(rows):
        _shade(t.cell(i, 0), "EEF3FB")
        _cell_text(t.cell(i, 0), k, True, size=10)
        _cell_text(t.cell(i, 1), v, size=10)
        t.cell(i, 0).width, t.cell(i, 1).width = d["Inches"](1.8), d["Inches"](4.9)
    doc.add_paragraph()
    _heading(doc, "Clave de respuestas y retroalimentación por opción", 1)
    _para(doc, "Las preguntas están numeradas en el orden en que aparecen en el video; el minuto indica cuándo debe mostrarse cada "
               "una. En H5P, marque como correcta la opción indicada y copie la retroalimentación en cada opción.", 10)
    tb = doc.add_table(len(qs) + 1, 3)
    _borders(tb)
    for j, h in enumerate(["N.º (min)", "Resp.", "Pregunta, opciones y retroalimentación por opción"]):
        _shade(tb.cell(0, j), NAVY_DOC)
        _cell_text(tb.cell(0, j), h, True, "FFFFFF", 10)
    for i, q in enumerate(qs):
        ops = q.get("opciones") or []
        letter = next((chr(65 + k) for k, o in enumerate(ops) if o.get("correcta")), "")
        _cell_text(tb.cell(i + 1, 0), "%d (%s)" % (i + 1, when(q)), size=10)
        _cell_text(tb.cell(i + 1, 1), letter, True, size=10)
        c = tb.cell(i + 1, 2)
        c.text = ""
        _run(c.paragraphs[0], q.get("enunciado") or "", bold=True, size=10)
        for k, o in enumerate(ops):
            pp = c.add_paragraph()
            _run(pp, "%s) %s " % (chr(65 + k), o.get("texto") or ""), size=10)
            _run(pp, "→ %s" % (o.get("retro") or ""), italic=True, size=10, color="3A4A68")
        for row in tb.rows:
            row.cells[0].width, row.cells[1].width, row.cells[2].width = d["Inches"](0.9), d["Inches"](0.6), d["Inches"](5.2)
    return _save(doc)


# ---------------------------------------------------------------- infografía
def docx_infografia(ig, meta):
    doc, d = _new_doc()
    _format_header(doc, d, "INFOGRAFÍA")
    _footer_note(doc, d, "NOTA: Al imprimir el presente documento, se convierte en COPIA NO CONTROLADA, a menos que se identifique "
                         "como COPIA CONTROLADA.")
    t = doc.add_table(4, 2)
    _borders(t, "000000")
    for i, (k, v) in enumerate([("Nombre profesor (a)", meta.get("teacher") or ""), ("Núcleo de aprendizaje", str(meta.get("nucleo_num") or "")),
                                ("Créditos Académicos", str(meta.get("credits") or "")), ("Tiempo aproximado de lectura", "4-6 minutos")]):
        _cell_text(t.cell(i, 0), k, True, size=10)
        _cell_text(t.cell(i, 1), v, size=10)
    doc.add_paragraph()
    terms = ig.get("terminos") or [{"termino": p.get("title"), "texto": p.get("text"), "icono": p.get("icon")}
                                   for p in ig.get("puntos") or []]
    tb = doc.add_table(6, 4)
    _borders(tb, "2F3D7A")

    def band(r, txt, sub=None):
        c = tb.cell(r, 0).merge(tb.cell(r, 3))
        _shade(c, "242E72")
        _cell_text(c, [txt] + ([sub] if sub else []), True, "FFFFFF", 10, d["WD_ALIGN_PARAGRAPH"].CENTER)

    c0 = tb.cell(0, 0).merge(tb.cell(0, 3))
    _cell_text(c0, "Formato de infografía", True, size=11, align=d["WD_ALIGN_PARAGRAPH"].CENTER)
    band(1, "Título/ tema")
    _cell_text(tb.cell(2, 0), "Título", True, size=10)
    _cell_text(tb.cell(2, 1).merge(tb.cell(2, 3)), ig.get("titulo") or "", True, size=10)
    pr = tb.cell(3, 0)
    _cell_text(pr, "Pregunta orientadora", True, size=10)
    _cell_text(tb.cell(3, 1).merge(tb.cell(3, 3)), ig.get("pregunta_orientadora") or ig.get("objetivo") or "", size=10)
    band(4, "Descripción inicial")
    # fila 5: texto orientador
    _cell_text(tb.cell(5, 0), ["Texto orientador", "Máximo 300 caracteres"], size=10)
    _cell_text(tb.cell(5, 1).merge(tb.cell(5, 3)), (ig.get("texto_orientador") or ig.get("dato_clave") or "")[:300], size=10)
    # Encabezado del contenido infográfico
    hdr = tb.add_row()
    hc = hdr.cells[0].merge(hdr.cells[3])
    _shade(hc, "242E72")
    _cell_text(hc, ["Contenido infográfico", "Complemente la descripción inicial con aportes significativos que refuercen el "
                    "planteamiento dado."], True, "FFFFFF", 9, d["WD_ALIGN_PARAGRAPH"].CENTER)
    cols = tb.add_row().cells
    for j, h in enumerate(["No.", "Término clave - principal", "Texto explicativo", "Imagen de apoyo"]):
        _shade(cols[j], "F2F2F2")
        _cell_text(cols[j], h, True, size=10, align=d["WD_ALIGN_PARAGRAPH"].CENTER, italic=True)
    for i, term in enumerate(terms):
        cells = tb.add_row().cells
        _cell_text(cells[0], str(i + 1), size=10, italic=True)
        _cell_text(cells[1], (term.get("termino") or "")[:40], size=10, italic=True)
        _cell_text(cells[2], (term.get("texto") or "")[:260], size=10)
        cells[3].text = ""
        try:
            png = visual.illustration_png(term.get("icono"), term.get("etiqueta") or "", 600)
            cells[3].paragraphs[0].add_run().add_picture(io.BytesIO(png), width=d["Inches"](1.9))
        except Exception:  # noqa: BLE001
            _cell_text(cells[3], term.get("etiqueta") or "", size=9)
    widths = [0.45, 1.6, 2.7, 2.1]
    for row in tb.rows:
        for j, c in enumerate(row.cells[:4]):
            c.width = d["Inches"](widths[j])
    return _save(doc)


# ------------------------------------------------------------ caso integrador
def docx_caso(caso, meta):
    doc, d = _new_doc()
    _format_header(doc, d, "CASO DE ESTUDIO INTEGRADOR")
    t = doc.add_table(3, 2)
    _borders(t, "000000")
    for i, (k, v) in enumerate([("Nombre del curso", meta.get("course") or ""), ("Nombre del caso de estudio", caso.get("titulo") or ""),
                                ("Tiempo sugerido para su realización (en horas)", "%s horas" % (caso.get("tiempo_horas") or 12))]):
        _cell_text(t.cell(i, 0), k, True, size=10)
        _cell_text(t.cell(i, 1), v, True, size=11)
    doc.add_paragraph()
    _para(doc, (caso.get("titulo_seccion") or "CASO DE ESTUDIO INTEGRADOR").upper(), bold=True)
    for par in re.split(r"\n\s*\n", caso.get("contexto") or ""):
        if par.strip():
            _para(doc, par.strip(), align=d["WD_ALIGN_PARAGRAPH"].JUSTIFY)
    _para(doc, "INDICACIONES PARA LOS ESTUDIANTES:", bold=True)
    if caso.get("introduccion_indicaciones"):
        _para(doc, caso["introduccion_indicaciones"], align=d["WD_ALIGN_PARAGRAPH"].JUSTIFY)
    _bullets(doc, caso.get("indicaciones") or [], numbered=True)
    if caso.get("entregables"):
        _para(doc, "Los entregables de esta parte son los siguientes:")
        _bullets(doc, caso["entregables"])
    if caso.get("cierre"):
        _para(doc, caso["cierre"])
    if caso.get("solucion"):
        _para(doc, "SOLUCIÓN DEL CASO", bold=True)
        _para(doc, "El docente debe verificar que la solución produzca el comportamiento descrito a continuación.")
        _data_table(doc, ["Escenario", "Acción / petición", "Resultado esperado"],
                    [[s.get("escenario", ""), s.get("accion", ""), s.get("resultado", "")] for s in caso["solucion"]],
                    [1.5, 2.6, 2.6])
    if caso.get("revision_docente"):
        _para(doc, "Además, el docente debe revisar: " + " ".join("(%d) %s;" % (i + 1, x) for i, x in enumerate(caso["revision_docente"])))
    rub = caso.get("rubrica") or []
    if rub:
        doc.add_paragraph().add_run().add_break(d["WD_BREAK"].PAGE)
        total = sum(float(r.get("puntaje") or 0) for r in rub) or 5.0
        _para(doc, "RÚBRICA DE EVALUACIÓN – %s" % (caso.get("titulo") or "").upper(), bold=True, align=d["WD_ALIGN_PARAGRAPH"].CENTER)
        _para(doc, "Peso total: %s de la nota del curso. Cada criterio se califica en tres niveles (BUENO = puntaje completo, "
                   "REGULAR = 60 %% del puntaje, INSUFICIENTE = 0). Puntaje máximo: %s." % (
                       caso.get("peso") or "—", ("%.1f" % total).replace(".", ",")), 10)
        tb = doc.add_table(2 + 2 * len(rub), 4)
        _borders(tb, "000000")
        C = d["WD_ALIGN_PARAGRAPH"].CENTER
        for j, h in enumerate(["NIVELES", "BUENO", "REGULAR", "INSUFICIENTE"]):
            _cell_text(tb.cell(0, j), h, True, "2F4B9A", 9, C)
        for j, h in enumerate(["CRITERIOS", "Puntaje completo (100 %)", "Puntaje parcial (60 %)", "Sin puntaje (0 %)"]):
            _cell_text(tb.cell(1, j), h, False, "2F4B9A", 9, C)
        for i, r in enumerate(rub):
            row = 2 + 2 * i
            pts = float(r.get("puntaje") or 0)
            cr = tb.cell(row, 0).merge(tb.cell(row + 1, 0))
            _cell_text(cr, r.get("criterio") or "", size=9)
            for j, k in enumerate(("bueno", "regular", "insuficiente")):
                _cell_text(tb.cell(row, j + 1), r.get(k) or "", size=9, align=C)
            for j, f in enumerate((1, 0.6, 0)):
                _cell_text(tb.cell(row + 1, j + 1), ("%.1f" % (pts * f)).replace(".", ",") if f else "0", size=9, align=C)
    return _save(doc)
