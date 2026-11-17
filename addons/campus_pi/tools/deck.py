# -*- coding: utf-8 -*-
"""Diapositivas y escenas de video con el formato institucional del Politécnico.

Una diapositiva normalizada tiene:
    layout      portada | puntos | codigo | tabla | proceso | comparacion | cita | cierre
    title, subtitle, points[], code, code_lang, table{headers, rows}, icon, icon_label,
    narration   texto que dice la voz (conversacional, como lo diría el docente)

Acepta también el formato anterior ({title, lead, points}) para no romper cursos existentes.
"""
import re

from . import visual

LAYOUTS = ("portada", "puntos", "codigo", "tabla", "proceso", "comparacion", "cita", "cierre")
MAX_POINT = 160


def _s(v, n=300):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def normalize_slide(raw, index=0, total=1):
    if not isinstance(raw, dict):
        return None
    title = _s(raw.get("title") or raw.get("titulo"), 120)
    if not title:
        return None
    points = [_s(p, MAX_POINT) for p in (raw.get("points") or raw.get("puntos") or []) if _s(p)][:6]
    lead = _s(raw.get("subtitle") or raw.get("subtitulo") or raw.get("lead"), 200)
    code = str(raw.get("code") or raw.get("codigo") or "").strip("\n")[:2500]
    table = raw.get("table") or raw.get("tabla") or {}
    headers, rows = [], []
    if isinstance(table, dict):
        headers = [_s(h, 60) for h in (table.get("headers") or table.get("encabezados") or [])][:5]
        for r in (table.get("rows") or table.get("filas") or [])[:7]:
            if isinstance(r, (list, tuple)):
                rows.append([_s(c, 140) for c in r][:len(headers) or 5])
    layout = _s(raw.get("layout") or raw.get("tipo"), 20).lower()
    if layout not in LAYOUTS:
        if index == 0:
            layout = "portada"
        elif code:
            layout = "codigo"
        elif headers and rows:
            layout = "tabla"
        elif index == total - 1 and total > 2:
            layout = "cierre"
        else:
            layout = "puntos"
    if layout == "codigo" and not code:
        layout = "puntos"
    if layout == "tabla" and not (headers and rows):
        layout = "puntos"
    icon_label = _s(raw.get("icon_label") or raw.get("etiqueta"), 34)
    icon = visual.pick_icon(raw.get("icon") or raw.get("icono"), " ".join([title, lead] + points))
    out = {
        "layout": layout, "title": title, "subtitle": lead, "points": points, "code": code,
        "code_lang": _s(raw.get("code_lang") or raw.get("lenguaje"), 20), "table": {"headers": headers, "rows": rows},
        "icon": icon, "icon_label": icon_label,
        "narration": _s(raw.get("narration") or raw.get("narracion") or raw.get("guion"), 3000),
    }
    # compatibilidad: plantillas antiguas leen 'lead'
    out["lead"] = out["subtitle"]
    return out


def normalize(slides):
    raw = [s for s in (slides or []) if isinstance(s, dict)]
    out = []
    for i, s in enumerate(raw):
        n = normalize_slide(s, i, len(raw))
        if n:
            out.append(n)
    return out


# ------------------------------------------------------------ narración
_OPENERS = ["Empecemos por", "Ahora veamos", "Sigamos con", "Pasemos a", "Revisemos", "Detengámonos en"]
_JOIN = ["Primero,", "Además,", "También,", "Por otra parte,", "Y por último,"]


def _lc(s):
    """Minúscula inicial salvo siglas o nombres propios técnicos (SLF4J, HTTP, Spring…)."""
    if len(s) > 1 and s[0].isupper() and s[1].islower() and not re.match(r"^[A-Z][a-z]+[A-Z]", s):
        return s[0].lower() + s[1:]
    return s


def _sentence(p):
    p = p.strip().rstrip(".;:")
    if not p:
        return ""
    return p[0].upper() + p[1:] + "."


def narration(slide, index=0, total=1, context=""):
    """Texto hablado de la diapositiva. Si el agente no lo escribió, se arma uno conversacional
    a partir de los puntos (en lugar de leer la lista de forma mecánica)."""
    if slide.get("narration"):
        return slide["narration"]
    title = slide.get("title") or ""
    pts = slide.get("points") or []
    sub = slide.get("subtitle") or ""
    if slide.get("layout") == "portada" or index == 0:
        txt = "Hola, te doy la bienvenida. En este recorrido vamos a trabajar el tema %s." % title.rstrip(".")
        if sub:
            txt += " %s" % _sentence(sub)
        if pts:
            txt += " La meta es clara: %s" % _lc(_sentence(pts[0]))
        txt += " Toma nota de las ideas clave y, si te surge una duda, pregúntale al tutor."
        return txt
    if slide.get("layout") == "cierre" or (index == total - 1 and total > 2):
        txt = "Para cerrar, recapitulemos. "
        txt += " ".join(_sentence(p) for p in pts[:4])
        return txt + " Muy bien, ya tienes las bases. Continúa con las actividades del núcleo."
    opener = _OPENERS[index % len(_OPENERS)]
    txt = "%s %s." % (opener, _lc(title.rstrip(".")) if title else "este tema")
    if sub:
        txt += " " + _sentence(sub)
    if slide.get("layout") == "codigo":
        txt += " Observa el ejemplo de código en pantalla y fíjate en cómo se aplica la idea paso a paso."
    if slide.get("layout") == "tabla":
        txt += " En la tabla puedes comparar cada caso con su respuesta adecuada."
    for k, p in enumerate(pts[:5]):
        lead = _JOIN[min(k, len(_JOIN) - 1)] if len(pts) > 1 else ""
        if k == len(pts) - 1 and len(pts) > 1:
            lead = "Y por último,"
        s = _sentence(p)
        txt += " %s %s" % (lead, _lc(s) if lead else s)
    return re.sub(r"\s+", " ", txt).strip()


# --------------------------------------------------- texto apto para voz
_SYMBOLS = [
    (r"https?://\S+", " el enlace que encuentras en el material "),
    (r"@(?=[A-Za-z])", " arroba "),
    (r"(\d)\s*%", r"\1 por ciento"),
    (r"\s->\s|→", ", luego, "),
    (r"\be\.\s*g\.", "por ejemplo"),
    (r"\bp\.\s*ej\.", "por ejemplo"),
    (r"\betc\.", "etcétera"),
    (r"&", " y "),
    (r"[`*_#>|]", " "),
    (r"\{id\}", " i de "),
    (r"\{\}", " llaves "),
    (r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", " "),
]


def speakable(text):
    """Limpia el texto para que la voz lo lea con naturalidad (sin símbolos ni URL)."""
    t = str(text or "")
    for pat, rep in _SYMBOLS:
        t = re.sub(pat, rep, t)
    t = re.sub(r"\s+([,.;:])", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


def words(text):
    return len(re.findall(r"\w+", text or ""))


def timeline(slides, wpm=145):
    """Minuto aproximado en que inicia cada escena (útil para ubicar preguntas en H5P)."""
    t, out = 0.0, []
    for i, s in enumerate(slides):
        out.append(int(round(t * 60)))
        t += max(words(narration(s, i, len(slides))), 25) / float(wpm) + 2.0 / 60
    return out, int(round(t * 60))


def mmss(seconds):
    return "%02d:%02d" % (seconds // 60, seconds % 60)
