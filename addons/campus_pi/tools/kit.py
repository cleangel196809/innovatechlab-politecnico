# -*- coding: utf-8 -*-
"""Kit de materiales de un núcleo con la estructura de los modelos del Politécnico.

El agente devuelve datos estructurados; aquí se arma el HTML que ve el estudiante en el aula. Los
mismos datos alimentan los documentos Word/PowerPoint (tools/office.py).
"""
import re

from markupsafe import escape as _esc

from . import deck as deck_tools


def e(t):
    return str(_esc(t or ""))


def _s(v, n=4000):
    return str(v or "").strip()[:n]


def _list(v, n=20):
    return [_s(x, 1200) for x in (v or []) if _s(x)][:n]


def clean_kit(data):
    """Normaliza lo que devuelve el modelo (tolerante a campos faltantes)."""
    data = data if isinstance(data, dict) else {}
    lec = data.get("lectura") if isinstance(data.get("lectura"), dict) else {}
    kit = {
        "lectura": {
            "titulo": _s(lec.get("titulo"), 200), "resumen": _s(lec.get("resumen"), 400),
            "presentacion": _s(lec.get("presentacion"), 3000), "logros": _list(lec.get("logros"), 8),
            "secciones_html": _s(lec.get("secciones_html") or lec.get("html"), 60000),
            "buenas_practicas": _list(lec.get("buenas_practicas"), 10),
            "casos": [{"titulo": _s(c.get("titulo"), 120), "texto": _s(c.get("texto"), 1200)}
                      for c in (lec.get("casos") or []) if isinstance(c, dict) and c.get("texto")][:4],
            "glosario": [{"termino": _s(g.get("termino"), 80), "significado": _s(g.get("significado"), 400)}
                         for g in (lec.get("glosario") or []) if isinstance(g, dict) and g.get("termino")][:16],
            "referencias": _list(lec.get("referencias"), 15),
        },
    }
    bib = data.get("bibliografia") if isinstance(data.get("bibliografia"), dict) else {}
    kit["bibliografia"] = {
        "principal": [{k: _s(b.get(k), 600) for k in ("titulo", "autor", "url", "tema", "paginas", "referencia")}
                      for b in bib.get("principal") or [] if isinstance(b, dict) and b.get("titulo")][:4],
        "complementaria": [{k: _s(b.get(k), 600) for k in ("titulo", "autor", "url", "referencia")}
                           for b in bib.get("complementaria") or [] if isinstance(b, dict) and b.get("titulo")][:10],
    }
    caso = data.get("caso") if isinstance(data.get("caso"), dict) else {}
    if caso.get("titulo") or caso.get("contexto"):
        kit["caso"] = {
            "titulo": _s(caso.get("titulo"), 200), "tiempo_horas": _s(caso.get("tiempo_horas"), 10) or "12",
            "peso": _s(caso.get("peso"), 30), "contexto": _s(caso.get("contexto"), 4000),
            "introduccion_indicaciones": _s(caso.get("introduccion_indicaciones"), 1500),
            "indicaciones": _list(caso.get("indicaciones"), 12), "entregables": _list(caso.get("entregables"), 8),
            "cierre": _s(caso.get("cierre"), 600),
            "solucion": [{k: _s(x.get(k), 400) for k in ("escenario", "accion", "resultado")}
                         for x in caso.get("solucion") or [] if isinstance(x, dict)][:10],
            "revision_docente": _list(caso.get("revision_docente"), 6),
            "rubrica": [{"criterio": _s(r.get("criterio"), 200), "bueno": _s(r.get("bueno"), 500),
                         "regular": _s(r.get("regular"), 500), "insuficiente": _s(r.get("insuficiente"), 500),
                         "puntaje": _num(r.get("puntaje"))}
                        for r in caso.get("rubrica") or [] if isinstance(r, dict) and r.get("criterio")][:8],
        }
    return kit


def _num(v):
    try:
        return round(float(str(v).replace(",", ".")), 2)
    except (TypeError, ValueError):
        return 1.0


def clean_activity(act):
    act = act if isinstance(act, dict) else {}
    qs = []
    for q in act.get("preguntas") or []:
        if not isinstance(q, dict) or not q.get("enunciado"):
            continue
        ops = [{"texto": _s(o.get("texto"), 500), "correcta": bool(o.get("correcta")), "retro": _s(o.get("retro"), 600)}
               for o in q.get("opciones") or [] if isinstance(o, dict) and o.get("texto")][:5]
        if len(ops) < 2 or sum(o["correcta"] for o in ops) != 1:
            continue
        qs.append({"escena": q.get("escena") or 1, "enunciado": _s(q.get("enunciado"), 1200), "opciones": ops})
    return {"titulo": _s(act.get("titulo"), 200), "objetivo": _s(act.get("objetivo"), 800),
            "instruccion": _s(act.get("instruccion"), 800), "preguntas": qs[:20]}


# --------------------------------------------------------------- HTML aula
def lectura_html(lec):
    out = []
    if lec.get("presentacion"):
        out.append("<h3>Presentación</h3>")
        out += ["<p>%s</p>" % e(p.strip()) for p in re.split(r"\n\s*\n", lec["presentacion"]) if p.strip()]
    if lec.get("logros"):
        out.append("<div class='cp-callout'><b>Lo que lograrás en este núcleo</b><ul>%s</ul></div>" % "".join(
            "<li>%s</li>" % e(x) for x in lec["logros"]))
    if lec.get("secciones_html"):
        out.append(lec["secciones_html"])
    if lec.get("buenas_practicas"):
        out.append("<h3>Buenas prácticas para recordar</h3><ul>%s</ul>" % "".join(
            "<li>%s</li>" % e(x) for x in lec["buenas_practicas"]))
    if lec.get("casos"):
        out.append("<h3>Casos para reflexionar</h3>")
        for i, c in enumerate(lec["casos"], 1):
            out.append("<div class='cp-callout cp-callout-case'><b>Caso %d. %s</b><p>%s</p></div>" % (
                i, e(c["titulo"]), e(c["texto"])))
    if lec.get("glosario"):
        out.append("<h3>Glosario</h3><table class='table'><tr><th>Término</th><th>Significado</th></tr>%s</table>" % "".join(
            "<tr><td><b>%s</b></td><td>%s</td></tr>" % (e(g["termino"]), e(g["significado"])) for g in lec["glosario"]))
    if lec.get("referencias"):
        out.append("<h3>Referencias</h3>%s" % "".join(
            "<p class='cp-ref'>%s</p>" % re.sub(r"(https?://[^\s<]+)", r"<a href='\1' target='_blank'>\1</a>", e(r))
            for r in lec["referencias"]))
    return "".join(out)


def caso_html(caso):
    out = []
    if caso.get("contexto"):
        out.append("<h4>El caso</h4>")
        out += ["<p>%s</p>" % e(p.strip()) for p in re.split(r"\n\s*\n", caso["contexto"]) if p.strip()]
    if caso.get("indicaciones"):
        out.append("<h4>Indicaciones</h4>")
        if caso.get("introduccion_indicaciones"):
            out.append("<p>%s</p>" % e(caso["introduccion_indicaciones"]))
        out.append("<ol>%s</ol>" % "".join("<li>%s</li>" % e(x) for x in caso["indicaciones"]))
    if caso.get("entregables"):
        out.append("<h4>Entregables</h4><ul>%s</ul>" % "".join("<li>%s</li>" % e(x) for x in caso["entregables"]))
    if caso.get("cierre"):
        out.append("<p>%s</p>" % e(caso["cierre"]))
    rub = caso.get("rubrica") or []
    if rub:
        total = sum(r["puntaje"] for r in rub)
        out.append("<h4>Rúbrica de evaluación%s</h4>" % (" (%s de la nota)" % e(caso["peso"]) if caso.get("peso") else ""))
        out.append("<p class='cp-small'>BUENO = puntaje completo · REGULAR = 60 %% · INSUFICIENTE = 0. Puntaje máximo: %s.</p>" %
                   ("%.1f" % total).replace(".", ","))
        out.append("<table class='table'><tr><th>Criterio</th><th>BUENO</th><th>REGULAR</th><th>INSUFICIENTE</th></tr>%s</table>" % "".join(
            "<tr><td><b>%s</b></td><td>%s<br/><small>%s</small></td><td>%s<br/><small>%s</small></td><td>%s<br/><small>0</small></td></tr>" % (
                e(r["criterio"]), e(r["bueno"]), ("%.1f" % r["puntaje"]).replace(".", ","), e(r["regular"]),
                ("%.1f" % (r["puntaje"] * .6)).replace(".", ","), e(r["insuficiente"])) for r in rub))
    return "".join(out)


def actividad_html(act):
    out = []
    if act.get("objetivo"):
        out.append("<p><b>Objetivo:</b> %s</p>" % e(act["objetivo"]))
    if act.get("instruccion"):
        out.append("<p>%s</p>" % e(act["instruccion"]))
    return "".join(out) or "<p>Resuelve los casos y revisa la retroalimentación de cada opción.</p>"


def guion_html(slides):
    starts, _t = deck_tools.timeline(slides)
    return "".join("<h4>Escena %d. %s <small>(%s)</small></h4><p>%s</p>" % (
        i + 1, e(s["title"]), deck_tools.mmss(starts[i]), e(deck_tools.narration(s, i, len(slides))))
        for i, s in enumerate(slides))
