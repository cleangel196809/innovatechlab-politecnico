# -*- coding: utf-8 -*-
"""Parser mínimo de formato GIFT (Moodle) para preguntas de opción múltiple.

Permite migrar los cuestionarios que ya existen en el aula virtual Moodle del PI.
"""
import re

_ESC = {"\\:": ":", "\\=": "=", "\\~": "~", "\\#": "#", "\\{": "{", "\\}": "}"}


def _unescape(s):
    for k, v in _ESC.items():
        s = s.replace(k, v)
    return s.strip()


def _split_unescaped(s, chars):
    """Divide s en tokens que empiezan por un carácter de `chars` no escapado."""
    parts, cur, i = [], "", 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            cur += s[i:i + 2]
            i += 2
            continue
        if c in chars:
            if cur.strip():
                parts.append(cur)
            cur = c
        else:
            cur += c
        i += 1
    if cur.strip():
        parts.append(cur)
    return parts


def parse_gift(text):
    """Devuelve preguntas de opción múltiple. Las líneas ``$CATEGORY: Dominio | Núcleo 2`` asignan
    el dominio de la certificación (y opcionalmente el núcleo) a las preguntas siguientes."""
    text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    questions = []
    category = None
    for block in re.split(r"\n\s*\n(?=\s*::|\s*\$CATEGORY|\s*[^\s{])", text):
        block = block.strip()
        while block.startswith("$CATEGORY:"):
            line, _sep, block = block.partition("\n")
            category = line.split(":", 1)[1].strip()
            category = re.sub(r"^\$(course|system)\$/", "", category).strip() or None
            block = block.strip()
        if "{" not in block:
            continue
        m = re.match(r"^(?:::(?P<title>.*?)::)?(?P<stem>.*?)(?<!\\)\{(?P<body>.*)(?<!\\)\}\s*$", block, re.S)
        if not m:
            continue
        stem = _unescape(re.sub(r"^\[\w+\]", "", m.group("stem").strip()))
        options = []
        general = ""
        body = m.group("body")
        if "####" in body:
            body, general = body.split("####", 1)
        for tok in _split_unescaped(body, "=~"):
            correct = tok.startswith("=")
            tok = tok[1:]
            w = re.match(r"^%(-?\d+(?:\.\d+)?)%", tok)
            if w:
                correct = float(w.group(1)) > 0
                tok = tok[w.end():]
            fb = ""
            pieces = re.split(r"(?<!\\)#", tok, maxsplit=1)
            if len(pieces) == 2:
                tok, fb = pieces
            options.append({"text": _unescape(tok), "correct": correct, "feedback": _unescape(fb)})
        if len(options) >= 2 and any(o["correct"] for o in options):
            explanation = _unescape(general) or next((o["feedback"] for o in options if o["correct"]), "")
            item = {"title": (m.group("title") or "").strip(), "question": stem,
                    "explanation": explanation, "options": options}
            if category:
                dom, _sep, nuc = category.partition("|")
                item["domain"] = dom.strip()
                m_n = re.search(r"\d+", nuc)
                if m_n:
                    item["nucleo"] = int(m_n.group())
            questions.append(item)
    return questions
