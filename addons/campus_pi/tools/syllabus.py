# -*- coding: utf-8 -*-
"""Lector del syllabus institucional del Politécnico Internacional (formato PI-GA-FT-141).

Convierte el DOCX (o el texto de un PDF/TXT) en una estructura que el agente usa como base:

{
  "asignatura", "programa", "area", "modalidad", "creditos", "horas", "prerrequisitos",
  "resultado_aprendizaje", "perfil_docente", "descripcion", "competencias", "producto",
  "objetivos": [str], "contenidos", "infraestructura",
  "nucleos": [{"numero", "titulo", "temas": [str], "objetivo", "estrategias": [str], "criterios": [str]}],
  "evaluacion": [{"criterios", "evidencia", "cuando", "para_que", "instrumento"}],
  "bibliografia": [str], "cibergrafia": [str], "texto": str
}

No depende de Odoo para poder probarse por separado.
"""
import io
import re
import unicodedata
import zipfile
from xml.etree import ElementTree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().upper()


def _clean(s):
    return re.sub(r"\s+", " ", (s or "").replace(" ", " ")).strip(" \t•·-–")


def _par_text(p):
    out = []
    for n in p.iter():
        if n.tag == W + "t":
            out.append(n.text or "")
        elif n.tag == W + "tab":
            out.append(" ")
        elif n.tag in (W + "br", W + "cr"):
            out.append("\n")
    return "".join(out)


def _cell_lines(tc):
    lines = []
    for p in tc.iter(W + "p"):
        for part in _par_text(p).split("\n"):
            part = _clean(part)
            if part:
                lines.append(part)
    return lines


def _empty():
    return {
        "asignatura": "", "programa": "", "area": "", "periodo": "", "modalidad": "", "creditos": "",
        "horas": "", "prerrequisitos": "", "resultado_aprendizaje": "", "perfil_docente": "",
        "descripcion": "", "competencias": "", "producto": "", "objetivos": [], "contenidos": "",
        "infraestructura": "", "nucleos": [], "evaluacion": [], "bibliografia": [], "cibergrafia": [],
        "texto": "",
    }


IDENT = {
    "ASIGNATURA": "asignatura", "AREA DE DESEMPENO": "area", "PERIODO": "periodo",
    "MODALIDAD": "modalidad", "CREDITOS": "creditos", "INTENSIDAD HORARIA": "horas",
    "PRERREQUISITOS": "prerrequisitos", "RESULTADO DE APRENDIZAJE": "resultado_aprendizaje",
    "PERFIL DOCENTE": "perfil_docente",
}


def parse_docx(raw):
    data = _empty()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        root = ElementTree.fromstring(z.read("word/document.xml"))
    body = root.find(W + "body")
    paragraphs, section = [], None
    blocks = {"descripcion": [], "bibliografia": [], "cibergrafia": []}
    for el in body:
        if el.tag == W + "p":
            txt = _clean(_par_text(el))
            if not txt:
                continue
            paragraphs.append(txt)
            n = _norm(txt)
            if n.startswith("PROGRAMA:"):
                data["programa"] = txt.split(":", 1)[1].strip()
            if "DESCRIPCION DEL CURSO" in n:
                section = "descripcion"
                continue
            if n.startswith("BIBLIOGRAFIA"):
                section = "bibliografia"
                continue
            if n.startswith("CIBERGRAFIA") or n.startswith("WEBGRAFIA"):
                section = "cibergrafia"
                continue
            if re.match(r"^(\d+\.\s*)?(ALCANCE|TEMATICAS|ALINEACION|CRITERIOS DE EVALUACION|ACUERDOS)", n):
                section = None
                continue
            if section:
                blocks[section].append(txt)
        elif el.tag == W + "tbl":
            rows = [[_cell_lines(tc) for tc in tr.findall(W + "tc")] for tr in el.findall(W + "tr")]
            for r in rows:
                paragraphs.append(" | ".join(" ".join(c) for c in r))
            _parse_table(rows, data)
    data["descripcion"] = "\n\n".join(blocks["descripcion"])
    data["bibliografia"] = blocks["bibliografia"]
    data["cibergrafia"] = blocks["cibergrafia"]
    data["texto"] = "\n".join(paragraphs)
    return data


def _parse_table(rows, data):
    if not rows:
        return
    head = [_norm(" ".join(c)) for c in rows[0]]
    joined = " ".join(head)
    # Identificación (2 columnas: etiqueta / valor)
    if any(len(r) == 2 and _norm(" ".join(r[0])) in IDENT for r in rows):
        for r in rows:
            if len(r) >= 2:
                key = IDENT.get(_norm(" ".join(r[0])))
                if key and not data.get(key):
                    data[key] = " ".join(r[1])
        return
    # Alcance (1 columna con subtítulos 3.1 ... 3.4)
    if any(len(r) == 1 and _norm(" ".join(r[0])).startswith("3.1") for r in rows):
        current = None
        for r in rows:
            txt = " ".join(r[0]) if r else ""
            n = _norm(txt)
            if re.match(r"^3\.1\b", n):
                current = "competencias"
            elif re.match(r"^3\.2\b", n):
                current = "ra"
            elif re.match(r"^3\.3\b", n):
                current = "producto"
            elif re.match(r"^3\.4\b(?!\.)", n):
                current = "objetivos"
            elif current == "objetivos":
                for line in r[0]:
                    line = re.sub(r"^3\.4\.\d+\s*", "", line).strip()
                    if line:
                        data["objetivos"].append(line)
            elif current == "competencias":
                data["competencias"] = (data["competencias"] + " " + txt).strip()
            elif current == "ra" and not data["resultado_aprendizaje"]:
                data["resultado_aprendizaje"] = txt
            elif current == "producto":
                data["producto"] = (data["producto"] + " " + txt).strip()
        return
    # Temáticas
    if any(len(r) >= 2 and "CONOCIMIENTOS" in _norm(" ".join(r[0])) for r in rows):
        for r in rows:
            if len(r) >= 2:
                k = _norm(" ".join(r[0]))
                if "CONOCIMIENTOS" in k:
                    data["contenidos"] = " ".join(r[1])
                elif "INFRAESTRUCTURA" in k or "MEDIOS" in k:
                    data["infraestructura"] = " ".join(r[1])
        return
    # Alineación curricular
    if "NUCLEO" in joined and "TEMATICA" in joined:
        idx = {name: i for i, h in enumerate(head) for name, key in
               (("tema", "TEMATICA"), ("obj", "OBJETIVO"), ("est", "ESTRATEGIA"), ("crit", "CRITERIO"))
               if key in h}
        for r in rows[1:]:
            if not r or not any(r):
                continue
            num_txt = " ".join(r[0])
            m = re.search(r"\d+", num_txt)
            tema = r[idx["tema"]] if "tema" in idx and idx["tema"] < len(r) else []
            if not tema:
                continue
            # La primera línea es el título del núcleo; las demás, sus temas
            nuc = {
                "numero": int(m.group()) if m else len(data["nucleos"]) + 1,
                "titulo": tema[0],
                "temas": tema[1:],
                "objetivo": " ".join(r[idx["obj"]]) if "obj" in idx and idx["obj"] < len(r) else "",
                "estrategias": r[idx["est"]] if "est" in idx and idx["est"] < len(r) else [],
                "criterios": r[idx["crit"]] if "crit" in idx and idx["crit"] < len(r) else [],
            }
            data["nucleos"].append(nuc)
        return
    # Criterios de evaluación
    if "CRITERIO DE EVALUACION" in joined and ("INSTRUMENTO" in joined or "CUANDO" in joined):
        for r in rows[1:]:
            if len(r) >= 5:
                data["evaluacion"].append({
                    "criterios": r[0], "evidencia": " ".join(r[1]), "cuando": " ".join(r[2]),
                    "para_que": " ".join(r[3]), "instrumento": " ".join(r[4])})


NOISE = re.compile(r"(?im)^.*(NOTA: Al imprimir|COPIA NO CONTROLADA|^FORMATO\s*$|C[óo]digo:\s*PI-|Emisi[óo]n:|SYLLABUS DE ASIGNATURA|^P[áa]gina\b).*$")


def _between(t, start, end):
    m = re.search(start + r"\s*[:|]?\s*(.+?)\s*(?:" + end + r")", t, re.S | re.I)
    return _clean(m.group(1)) if m else ""


def parse_text(text):
    """Respaldo para PDF/TXT: heurísticas sobre el texto del formato PI-GA-FT-141."""
    data = _empty()
    data["texto"] = text or ""
    t = NOISE.sub(" ", (text or "").replace("|", " "))
    t = re.sub(r"P[áa]gina\s*\d+\s*de\s*\d+", " ", t)
    t = re.sub(r"[+=\-]{3,}[+=\-]*", " ", t)  # bordes de tablas en texto plano
    t = t.replace("\uf0b7", "\n• ").replace("▪", "\n• ")
    t = re.sub(r"[ \t]+", " ", t)
    flat = re.sub(r"\s*\n\s*", " ", t)
    data["asignatura"] = re.sub(r"^(ASIGNATURA\s*)+", "", _between(
        flat, r"IDENTIFICACI[ÓO]N DE LA ASIGNATURA", r"[ÁA]REA DE DESEMPE|PERIODO"))[:200]
    data["area"] = _between(flat, r"[ÁA]REA DE DESEMPE[ÑN]O", r"PERIODO")[:200]
    data["modalidad"] = _between(flat, r"MODALIDAD", r"CR[ÉE]DITOS")[:60]
    data["creditos"] = _between(flat, r"CR[ÉE]DITOS", r"INTENSIDAD")[:20]
    data["horas"] = _between(flat, r"INTENSIDAD HORARIA", r"PRERREQUISITOS")[:60]
    data["prerrequisitos"] = _between(flat, r"PRERREQUISITOS", r"RESULTADO DE APRENDIZAJE")[:200]
    data["resultado_aprendizaje"] = _between(flat, r"RESULTADO DE APRENDIZAJE", r"PERFIL DOCENTE")[:600]
    data["perfil_docente"] = _between(flat, r"PERFIL DOCENTE", r"VERSI[ÓO]N")[:400]
    data["descripcion"] = _between(flat, r"DESCRIPCI[ÓO]N DEL CURSO", r"\d\.\s*ALCANCE DE LA ASIGNATURA|ALCANCE DE LA ASIGNATURA")[:3000]
    data["competencias"] = _between(flat, r"3\.1\s*COMPETENCIAS", r"3\.2")[:800]
    data["producto"] = _between(flat, r"3\.3\s*PRODUCTO DE RESULTADO DE APRENDIZAJE", r"3\.4")[:600]
    data["contenidos"] = _between(flat, r"CONOCIMIENTOS ASOCIADOS\s*/?\s*CONTENIDOS", r"REQUERIMIENTOS")[:2000]
    data["infraestructura"] = _between(flat, r"MEDIOS EDUCATIVOS", r"\d\.\s*ALINEACI[ÓO]N|ALINEACI[ÓO]N CURRICULAR")[:800]
    m = re.search(r"PROGRAMA:\s*([^\n]+)", t)
    if m:
        data["programa"] = _clean(m.group(1))
    # Objetivos 3.4.x (pueden ocupar varias líneas)
    objs = list(re.finditer(r"3\.4\.(\d+)\s*", flat))
    for i, mo in enumerate(objs):
        end = objs[i + 1].start() if i + 1 < len(objs) else len(flat)
        chunk = flat[mo.end():end]
        chunk = re.split(r"\s\d\.\s*[A-ZÁÉÍÓÚ]{4,}|\bTEM[ÁA]TICAS PARA TRATAR|\bNÚCLEO\b", chunk)[0]
        txt = _clean(chunk)[:400]
        if len(txt) > 10:
            data["objetivos"].append(txt)
    # Núcleos explícitos ("Núcleo 1 – Título" al inicio de línea)
    seen = set()
    for m in re.finditer(r"(?m)^\s*N[ÚU]CLEO\s+(?:DE APRENDIZAJE\s+)?(\d+)\s*[.:–\-]\s*([A-ZÁÉÍÓÚ¿][^\n]{3,120})", t, re.I):
        num = int(m.group(1))
        title = re.split(r"[.?¿]", _clean(m.group(2)))[0][:110]
        if num in seen or not title or re.match(r"(?i)(verificar|utiliza|al finalizar)", title):
            continue
        seen.add(num)
        data["nucleos"].append({"numero": num, "titulo": title, "temas": [], "objetivo": "",
                                "estrategias": [], "criterios": []})
    data["nucleos"].sort(key=lambda n: n["numero"])
    # Sin núcleos explícitos: un núcleo por objetivo de aprendizaje
    if not data["nucleos"] and data["objetivos"]:
        for i, o in enumerate(data["objetivos"], 1):
            title = re.sub(r"^(Analizar|Explicar|Describir|Aplicar|Implementar|Identificar|Comprender|Diseñar|"
                           r"Desarrollar|Evaluar|Reconocer|Construir|Utilizar|Usar)\s+(c[óo]mo\s+se\s+)?", "", o, flags=re.I)
            title = re.split(r"[,.;]| mediante | utilizando | en entornos ", title)[0].strip()
            words = title.split()
            for j, w in enumerate(words[:3]):
                if j and w.lower() in ("la", "las", "el", "los"):
                    title = " ".join(words[j + 1:])
                    break
            title = re.sub(r"^(la|las|el|los)\s+", "", title, flags=re.I)
            title = (title[:1].upper() + title[1:])[:90] or "Unidad %s" % i
            data["nucleos"].append({"numero": i, "titulo": title, "temas": [], "objetivo": o,
                                    "estrategias": [], "criterios": []})
    for n in data["nucleos"]:
        if not n["objetivo"] and n["numero"] - 1 < len(data["objetivos"]):
            n["objetivo"] = data["objetivos"][n["numero"] - 1]
    # Reparte los contenidos entre los núcleos como temas
    sentences = [x.strip() for x in re.split(r"(?<=[.])\s+", data["contenidos"]) if len(x.strip()) > 3]
    if data["nucleos"] and sentences and not any(n["temas"] for n in data["nucleos"]):
        k = len(data["nucleos"])
        size = max(1, -(-len(sentences) // k))
        for i, n in enumerate(data["nucleos"]):
            n["temas"] = sentences[i * size:(i + 1) * size] or [n["titulo"]]
    m = (re.search(r"BIBLIOGRAF[ÍI]A SUGERIDA\s*(.+?)(?:(?:\d+\.\s*)?CIBERGRAF|WEBGRAF|\Z)", t, re.S | re.I)
         or re.search(r"\d\.\s*BIBLIOGRAF[ÍI]A\s*(.+?)(?:(?:\d+\.\s*)?CIBERGRAF|\Z)", t, re.S | re.I))
    if m:
        items = re.split(r"\n\s*[•*]\s*|\n\s*-\s+", m.group(1))
        if len(items) <= 1:
            items = m.group(1).split("\n")
        data["bibliografia"] = [_clean(x) for x in items if len(_clean(x)) > 8 and "http" not in x][:20]
    data["cibergrafia"] = sorted(set(u.rstrip(".,;") for u in re.findall(r"https?://[^\s)>\]]+", t)))[:30]
    return data


def parse(raw, filename):
    name = (filename or "").lower()
    if name.endswith(".docx"):
        return parse_docx(raw)
    return parse_text(raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else raw)


def summary(data, limit=12000):
    """Resumen compacto del syllabus para los prompts del agente."""
    lines = ["ASIGNATURA: %s" % data.get("asignatura"), "PROGRAMA: %s" % data.get("programa"),
             "MODALIDAD: %s · CRÉDITOS: %s · HORAS: %s" % (data.get("modalidad"), data.get("creditos"), data.get("horas")),
             "RESULTADO DE APRENDIZAJE: %s" % data.get("resultado_aprendizaje"),
             "COMPETENCIA: %s" % data.get("competencias"),
             "PRODUCTO: %s" % data.get("producto"),
             "DESCRIPCIÓN: %s" % (data.get("descripcion") or "")[:2500],
             "OBJETIVOS: " + " | ".join(data.get("objetivos") or []),
             "CONTENIDOS: %s" % data.get("contenidos")]
    for n in data.get("nucleos") or []:
        lines.append("NÚCLEO %s – %s. Temas: %s. Objetivo: %s. Criterios: %s" % (
            n["numero"], n["titulo"], "; ".join(n["temas"]), n["objetivo"], " ".join(n["criterios"])))
    for e in data.get("evaluacion") or []:
        lines.append("EVALUACIÓN %s: %s (%s)" % (e["cuando"], e["instrumento"], e["evidencia"]))
    if data.get("bibliografia"):
        lines.append("BIBLIOGRAFÍA: " + " | ".join(data["bibliografia"]))
    if data.get("cibergrafia"):
        lines.append("CIBERGRAFÍA: " + " | ".join(data["cibergrafia"]))
    out = "\n".join(l for l in lines if l and not l.endswith(": ") and not l.endswith(": None"))
    if len(out) < 400:
        out += "\n\nTEXTO DEL SYLLABUS:\n" + (data.get("texto") or "")
    return out[:limit]
