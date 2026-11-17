# -*- coding: utf-8 -*-
"""Ilustraciones institucionales de las diapositivas e infografías.

Cada ícono se define una sola vez con primitivas simples en una cuadrícula de 24x24 y se dibuja:
* como SVG (aula virtual), y
* como PNG con Pillow (PPTX y DOCX), con la misma composición del video modelo del Politécnico:
  mancha celeste de fondo, círculo principal azul oscuro con el ícono, dos círculos de acento
  (naranja y azul) y una etiqueta corta debajo.
"""
import io
import math
import re

NAVY = "#0B1F5B"
SKY = "#1E9BD7"
ORANGE = "#F5A623"
RED = "#D9453B"
GREEN = "#2E9E5B"
BLOB = "#E3EEF9"
WHITE = "#FFFFFF"


def _gear():
    pts = []
    for k in range(16):
        r = 8 if k % 2 == 0 else 6
        a = math.pi * 2 * k / 16
        pts.append((12 + r * math.cos(a), 12 + r * math.sin(a)))
    return [("poly", pts, "f"), ("circle", 12, 12, 2.6, "bg")]


# Primitivas: ("poly", [(x, y)…], "f"|"s"), ("line", [(x, y)…]), ("circle", cx, cy, r, "f"|"s"|"bg"),
# ("rect", x, y, w, h, "f"|"s"|"bg"). "f" relleno blanco, "s" trazo blanco, "bg" relleno del color del círculo.
ICONS = {
    "alerta": [("poly", [(12, 3), (22, 20), (2, 20)], "f"), ("rect", 11, 8.5, 2, 6.5, "bg"), ("circle", 12, 17.3, 1.2, "bg")],
    "rayo": [("poly", [(13.5, 2), (5, 13.5), (11, 13.5), (9.5, 22), (19, 9.5), (13, 9.5)], "f")],
    "codigo": [("line", [(8, 6), (2.5, 12), (8, 18)]), ("line", [(16, 6), (21.5, 12), (16, 18)]), ("line", [(14, 4), (10, 20)])],
    "jerarquia": [("rect", 9, 2.5, 6, 5, "f"), ("line", [(12, 7.5), (12, 11)]), ("line", [(4.5, 14), (4.5, 11), (19.5, 11), (19.5, 14)]),
                  ("line", [(12, 11), (12, 14)]), ("rect", 2, 14, 5, 5, "f"), ("rect", 9.5, 14, 5, 5, "f"), ("rect", 17, 14, 5, 5, "f")],
    "check": [("line", [(4, 12.5), (9.5, 18), (20, 6)])],
    "escudo": [("poly", [(12, 2), (20.5, 5.5), (20, 12), (12, 22), (4, 12), (3.5, 5.5)], "f"), ("line", [(8, 12), (11, 15), (16.5, 8.5)])],
    "datos": [("rect", 4, 3.5, 16, 17, "f"), ("rect", 4, 8.8, 16, 1.4, "bg"), ("rect", 4, 14, 16, 1.4, "bg"),
              ("circle", 7.2, 6.2, 1, "bg"), ("circle", 7.2, 11.6, 1, "bg"), ("circle", 7.2, 17.4, 1, "bg")],
    "engranaje": _gear(),
    "buscar": [("circle", 10, 10, 6, "s"), ("line", [(14.5, 14.5), (21, 21)])],
    "documento": [("poly", [(5, 2), (14, 2), (19, 7), (19, 22), (5, 22)], "f"), ("rect", 8, 10, 8, 1.6, "bg"),
                  ("rect", 8, 13.5, 8, 1.6, "bg"), ("rect", 8, 17, 5.5, 1.6, "bg")],
    "personas": [("circle", 8, 7.5, 3.3, "f"), ("circle", 16.5, 8.5, 2.8, "f"),
                 ("poly", [(2, 20), (2.8, 15), (5.5, 12.5), (10.5, 12.5), (13.2, 15), (14, 20)], "f"),
                 ("poly", [(14.5, 20), (15, 15.5), (16.5, 13.5), (19.5, 13.5), (21.5, 15.5), (22, 20)], "f")],
    "candado": [("rect", 4.5, 10.5, 15, 11, "f"), ("line", [(8, 11), (8, 7.5), (9.2, 4.6), (12, 3.4), (14.8, 4.6), (16, 7.5), (16, 11)]),
                ("circle", 12, 15.5, 1.7, "bg")],
    "grafica": [("rect", 3.5, 13, 4, 8, "f"), ("rect", 10, 8, 4, 13, "f"), ("rect", 16.5, 4, 4, 17, "f")],
    "nube": [("circle", 8, 14, 5, "f"), ("circle", 13.5, 10.5, 6, "f"), ("circle", 18, 15, 4, "f"), ("rect", 8, 14, 10, 5, "f")],
    "flujo": [("circle", 4.5, 12, 2.5, "f"), ("line", [(7.5, 12), (16.5, 12)]), ("line", [(13.5, 8.5), (17, 12), (13.5, 15.5)]),
              ("circle", 19.5, 12, 2.5, "f")],
    "idea": [("circle", 12, 9.5, 6.5, "f"), ("rect", 9, 15, 6, 3.5, "f"), ("rect", 9.8, 19.5, 4.4, 1.8, "f")],
    "objetivo": [("circle", 12, 12, 9, "s"), ("circle", 12, 12, 5.2, "s"), ("circle", 12, 12, 1.8, "f")],
    "libro": [("poly", [(2, 5), (11.3, 6.5), (11.3, 21), (2, 19.5)], "f"), ("poly", [(12.7, 6.5), (22, 5), (22, 19.5), (12.7, 21)], "f")],
    "bicho": [("circle", 12, 13.5, 5.6, "f"), ("circle", 12, 6.5, 3, "f"), ("line", [(6.5, 11), (2.5, 9)]), ("line", [(17.5, 11), (21.5, 9)]),
              ("line", [(6.3, 15.5), (2.5, 16.5)]), ("line", [(17.7, 15.5), (21.5, 16.5)]), ("line", [(12, 9), (12, 19)])],
    "llave": [("circle", 7.5, 12, 4.5, "s"), ("line", [(12, 12), (22, 12)]), ("line", [(18.5, 12), (18.5, 15.5)]), ("line", [(21.5, 12), (21.5, 15)])],
    "mano": [("rect", 6, 9, 3, 9, "f"), ("rect", 9.3, 4, 2.8, 12, "f"), ("rect", 12.4, 3, 2.8, 13, "f"), ("rect", 15.5, 5, 2.8, 11, "f"),
             ("rect", 6, 13, 12.3, 8, "f")],
    "reloj": [("circle", 12, 12, 9, "s"), ("line", [(12, 6.5), (12, 12), (16, 14.5)])],
    "servidor": [("rect", 3.5, 3, 17, 7, "f"), ("rect", 3.5, 13, 17, 7, "f"), ("circle", 7, 6.5, 1.2, "bg"), ("circle", 7, 16.5, 1.2, "bg")],
    "cohete": [("poly", [(12, 1.5), (15.5, 6), (15.5, 16), (8.5, 16), (8.5, 6)], "f"), ("circle", 12, 9, 1.8, "bg"),
               ("poly", [(8.5, 11), (5, 16.5), (8.5, 16)], "f"), ("poly", [(15.5, 11), (19, 16.5), (15.5, 16)], "f"),
               ("poly", [(10, 17.3), (14, 17.3), (12, 22)], "f")],
    "info": [("circle", 12, 6.5, 1.8, "f"), ("rect", 10.6, 10, 2.8, 10, "f")],
    "error": [("line", [(6, 6), (18, 18)]), ("line", [(18, 6), (6, 18)])],
    "prohibido": [("circle", 12, 12, 8.5, "s"), ("line", [(6, 18), (18, 6)])],
    "red": [("circle", 12, 4.5, 2.5, "f"), ("circle", 4.5, 18.5, 2.5, "f"), ("circle", 19.5, 18.5, 2.5, "f"),
            ("line", [(12, 7), (5.5, 16.5)]), ("line", [(12, 7), (18.5, 16.5)]), ("line", [(7, 18.5), (17, 18.5)])],
    "dinero": [("rect", 2, 6, 20, 12, "s"), ("circle", 12, 12, 3, "s")],
    "pregunta": [("line", [(8, 8.5), (9.5, 5), (12, 4), (14.5, 5), (16, 8), (15, 10.5), (12, 12.5), (12, 15)]), ("circle", 12, 19, 1.5, "f")],
    "terminal": [("rect", 2, 4, 20, 16, "s"), ("line", [(6, 9), (9.5, 12), (6, 15)]), ("line", [(11.5, 15.5), (17, 15.5)])],
    "estrella": [("poly", [(12 + 9 * math.cos(math.pi / 2 + k * math.pi / 5) * (1 if k % 2 == 0 else .45),
                            12 - 9 * math.sin(math.pi / 2 + k * math.pi / 5) * (1 if k % 2 == 0 else .45)) for k in range(10)], "f")],
}
ICON_NAMES = sorted(ICONS)

# Palabras que ayudan a elegir un ícono cuando el agente no lo indica
_HINTS = [
    ("alerta", "riesgo amenaza advertencia warning peligro falla fallo"), ("rayo", "excepción excepcion lanzar evento rápido"),
    ("codigo", "código codigo java python sintaxis programación api endpoint html clase método"),
    ("jerarquia", "jerarquía jerarquia herencia árbol arquitectura capas estructura organigrama"),
    ("check", "buenas prácticas validación verificar correcto aprobado"), ("escudo", "seguridad protección cifrado owasp"),
    ("datos", "base de datos sql tabla registro jpa postgres"), ("engranaje", "configuración configurar proceso automatización"),
    ("buscar", "diagnóstico diagnostico buscar analizar investigar traza depurar"), ("documento", "documento log registro informe archivo reporte"),
    ("personas", "equipo usuario cliente estudiante rol"), ("candado", "autenticación contraseña acceso privacidad"),
    ("grafica", "métrica métricas datos estadística resultados rendimiento"), ("nube", "nube cloud azure aws despliegue"),
    ("flujo", "flujo ciclo pasos proceso secuencia pipeline"), ("idea", "concepto idea introducción qué es"),
    ("objetivo", "objetivo meta resultado de aprendizaje logro"), ("libro", "lectura teoría referencia bibliografía glosario"),
    ("bicho", "bug error depuración debug defecto"), ("reloj", "tiempo cronograma duración"), ("servidor", "servidor backend infraestructura"),
    ("cohete", "despliegue lanzamiento siguiente próximo"), ("red", "red redes conexión http protocolo"), ("terminal", "consola comando terminal cli"),
    ("pregunta", "pregunta reflexión caso"), ("estrella", "resumen cierre logro certificación"),
]


def pick_icon(name=None, text=""):
    """Devuelve un nombre de ícono válido (el pedido o uno sugerido por el texto)."""
    name = (name or "").strip().lower()
    if name in ICONS:
        return name
    low = set(re.findall(r"\w+", (text or "").lower()))
    best, score = "idea", 0
    for icon, words in _HINTS:
        s = sum(1 for w in words.split() if len(w) > 2 and w in low)
        if s > score:
            best, score = icon, s
    return best


# ------------------------------------------------------------------ SVG
def _svg_shape(sh, scale, ox, oy, bg):
    kind = sh[0]
    if kind == "poly":
        pts = " ".join("%.1f,%.1f" % (ox + x * scale, oy + y * scale) for x, y in sh[1])
        if sh[2] == "f":
            return '<polygon points="%s" fill="#fff"/>' % pts
        return '<polygon points="%s" fill="none" stroke="#fff" stroke-width="%.1f" stroke-linejoin="round"/>' % (pts, 2 * scale)
    if kind == "line":
        pts = " ".join("%.1f,%.1f" % (ox + x * scale, oy + y * scale) for x, y in sh[1])
        return ('<polyline points="%s" fill="none" stroke="#fff" stroke-width="%.1f" stroke-linecap="round" '
                'stroke-linejoin="round"/>' % (pts, 2.2 * scale))
    if kind == "circle":
        _k, cx, cy, r, mode = sh
        if r <= 0:
            return ""
        if mode == "s":
            return '<circle cx="%.1f" cy="%.1f" r="%.1f" fill="none" stroke="#fff" stroke-width="%.1f"/>' % (
                ox + cx * scale, oy + cy * scale, r * scale, 2.2 * scale)
        return '<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s"/>' % (ox + cx * scale, oy + cy * scale, r * scale,
                                                                     bg if mode == "bg" else "#fff")
    if kind == "rect":
        _k, x, y, w, h, mode = sh
        if mode == "s":
            return '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%.1f" fill="none" stroke="#fff" stroke-width="%.1f"/>' % (
                ox + x * scale, oy + y * scale, w * scale, h * scale, 1.5 * scale, 2.2 * scale)
        return '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%.1f" fill="%s"/>' % (
            ox + x * scale, oy + y * scale, w * scale, h * scale, 1 * scale, bg if mode == "bg" else "#fff")
    return ""


def icon_svg(name, color=NAVY, size=24):
    """Ícono suelto (círculo de color con el glifo blanco)."""
    name = pick_icon(name)
    s = size / 24.0
    inner = "".join(_svg_shape(sh, s * .6, size * .2, size * .2, color) for sh in ICONS[name])
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" aria-hidden="true">'
            '<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s"/>%s</svg>') % (size, size, size, size, size / 2, size / 2, size / 2, color, inner)


def illustration_svg(name, label="", main=NAVY):
    """Composición del video modelo: mancha, círculo principal, acentos y etiqueta."""
    name = pick_icon(name, label)
    acc = {"alerta": RED, "rayo": RED, "error": RED, "prohibido": RED, "bicho": RED}.get(name, main)
    inner = "".join(_svg_shape(sh, 3.4, 159, 74, acc) for sh in ICONS[name])
    lab = ""
    if label:
        from xml.sax.saxutils import escape
        lab = ('<text x="200" y="232" text-anchor="middle" font-family="Montserrat,Segoe UI,Arial,sans-serif" '
               'font-size="15" font-weight="700" fill="%s">%s</text>') % (NAVY, escape(label[:34]))
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 260" class="cp-illu" role="img" aria-label="%s">'
            '<rect x="0" y="0" width="400" height="260" rx="18" fill="#fff"/>'
            '<circle cx="120" cy="70" r="88" fill="%s"/><circle cx="320" cy="210" r="78" fill="%s"/>'
            '<circle cx="200" cy="115" r="64" fill="%s"/>%s'
            '<circle cx="110" cy="62" r="22" fill="%s"/><circle cx="292" cy="58" r="20" fill="%s"/>'
            '<circle cx="330" cy="30" r="9" fill="%s" opacity=".5"/><circle cx="70" cy="200" r="8" fill="%s" opacity=".6"/>'
            '<circle cx="345" cy="120" r="4" fill="%s"/><circle cx="52" cy="128" r="4" fill="%s"/>%s</svg>') % (
        label or name, BLOB, BLOB, acc, inner, SKY, ORANGE, SKY, ORANGE, SKY, SKY, lab)


# ------------------------------------------------------------------ PNG
def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def illustration_png(name, label="", width=800):
    """Misma composición que illustration_svg, en PNG (para PPTX y DOCX)."""
    from PIL import Image, ImageDraw, ImageFont
    name = pick_icon(name, label)
    k = width / 400.0
    W, H = int(400 * k), int(260 * k)
    im = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=int(18 * k), fill=_hex("#FFFFFF"))

    def circ(cx, cy, r, col, alpha=255):
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(lay).ellipse([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k], fill=_hex(col) + (alpha,))
        im.alpha_composite(lay)

    acc = {"alerta": RED, "rayo": RED, "error": RED, "prohibido": RED, "bicho": RED}.get(name, NAVY)
    circ(120, 70, 88, BLOB)
    circ(320, 210, 78, BLOB)
    circ(200, 115, 64, acc)
    d = ImageDraw.Draw(im)
    s, ox, oy = 3.4, 159, 74
    white, bgc = _hex(WHITE), _hex(acc)

    def P(x, y):
        return ((ox + x * s) * k, (oy + y * s) * k)

    for sh in ICONS[name]:
        kind = sh[0]
        if kind == "poly":
            pts = [P(x, y) for x, y in sh[1]]
            if sh[2] == "f":
                d.polygon(pts, fill=white)
            else:
                d.line(pts + [pts[0]], fill=white, width=int(2 * s * k), joint="curve")
        elif kind == "line":
            pts = [P(x, y) for x, y in sh[1]]
            w = max(2, int(2.2 * s * k))
            d.line(pts, fill=white, width=w, joint="curve")
            for p in (pts[0], pts[-1]):
                d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=white)
        elif kind == "circle":
            _k, cx, cy, r, mode = sh
            if r <= 0:
                continue
            (x0, y0), (x1, y1) = P(cx - r, cy - r), P(cx + r, cy + r)
            if mode == "s":
                d.ellipse([x0, y0, x1, y1], outline=white, width=max(2, int(2.2 * s * k)))
            else:
                d.ellipse([x0, y0, x1, y1], fill=bgc if mode == "bg" else white)
        elif kind == "rect":
            _k, x, y, w, h, mode = sh
            (x0, y0), (x1, y1) = P(x, y), P(x + w, y + h)
            if mode == "s":
                d.rounded_rectangle([x0, y0, x1, y1], radius=int(1.5 * s * k), outline=white, width=max(2, int(2.2 * s * k)))
            else:
                rad = int(min(1 * s * k, (x1 - x0) / 2.5, (y1 - y0) / 2.5))
                d.rounded_rectangle([x0, y0, x1, y1], radius=max(rad, 0), fill=bgc if mode == "bg" else white)
    circ(110, 62, 22, SKY)
    circ(292, 58, 20, ORANGE)
    circ(330, 30, 9, SKY, 128)
    circ(70, 200, 8, ORANGE, 150)
    circ(345, 120, 4, SKY)
    circ(52, 128, 4, SKY)
    if label:
        d = ImageDraw.Draw(im)
        font = None
        for f in ("DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
            try:
                font = ImageFont.truetype(f, int(15 * k))
                break
            except OSError:
                continue
        font = font or ImageFont.load_default()
        txt = label[:34]
        tw = d.textlength(txt, font=font)
        d.text(((W - tw) / 2, 220 * k), txt, fill=_hex(NAVY), font=font)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()
