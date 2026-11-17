# -*- coding: utf-8 -*-
"""Material multimedia de las lecciones.

Resuelve qué mostrar en una lección de video, infografía o presentación:
1. Lo que cargó el docente (archivo o enlace), normalizado para que se vea
   embebido (YouTube, Vimeo, Google Drive, MP4, imágenes, PDF).
2. Si no hay nada cargado, material generado automáticamente a partir del
   contenido del núcleo (infografía y diapositivas narradas), para que la
   lección nunca quede en blanco.
"""
import mimetypes
import random
import re
from urllib.parse import parse_qs, urlparse

from lxml import html as lxml_html

from markupsafe import Markup

from odoo import models
from odoo.tools import html2plaintext

from ..tools import deck as deck_tools
from ..tools import visual

VIDEO_EXT = (".mp4", ".webm", ".ogg", ".ogv", ".mov", ".m4v")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
MAX_POINTS = 6


def _yt_id(url):
    """Devuelve el id de YouTube de cualquier forma de enlace, o None."""
    p = urlparse(url)
    host = (p.hostname or "").lower().replace("www.", "").replace("m.", "", 1)
    if host == "youtu.be":
        return p.path.strip("/").split("/")[0] or None
    if host in ("youtube.com", "youtube-nocookie.com", "music.youtube.com"):
        if p.path == "/watch":
            return (parse_qs(p.query).get("v") or [None])[0]
        m = re.match(r"^/(?:embed|shorts|live|v)/([\w-]{6,})", p.path)
        if m:
            return m.group(1)
    return None


def video_embed(url):
    """Normaliza un enlace de video. Retorna (tipo, src) con tipo iframe|video, o (None, None)."""
    url = (url or "").strip()
    if not url:
        return None, None
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    vid = _yt_id(url)
    if vid:
        return "iframe", "https://www.youtube-nocookie.com/embed/%s?rel=0" % vid
    p = urlparse(url)
    host = (p.hostname or "").lower().replace("www.", "")
    if host == "vimeo.com":
        m = re.match(r"^/(\d+)", p.path)
        if m:
            return "iframe", "https://player.vimeo.com/video/%s" % m.group(1)
    if host == "player.vimeo.com":
        return "iframe", url
    if host == "drive.google.com":
        m = re.search(r"/file/d/([\w-]+)", p.path) or re.search(r"[?&]id=([\w-]+)", url)
        if m:
            return "iframe", "https://drive.google.com/file/d/%s/preview" % m.group(1)
    if p.path.lower().endswith(VIDEO_EXT):
        return "video", url
    # Teams/Stream/SharePoint/otros: se intenta embebido
    return "iframe", url


def _short(text, limit=130):
    """Recorta un texto para pantalla sin cortar palabras (y sin dos puntos colgando)."""
    t = re.sub(r"\s+", " ", text or "").strip()
    if len(t) <= limit:
        return t.rstrip(":")
    cut = t[:limit]
    for sep in (". ", "; ", ": ", ", "):
        k = cut.rfind(sep)
        if k > limit * .55:
            return cut[:k].rstrip(",;:") + ("." if sep == ". " else "…")
    return cut[:cut.rfind(" ")].rstrip(",;:") + "…"


class CampusLessonMedia(models.Model):
    _inherit = "campus.lesson"

    # ------------------------------------------------------------ archivo
    def attachment_mimetype(self):
        self.ensure_one()
        name = (self.attachment_name or "").lower()
        mime = mimetypes.guess_type(name)[0] if name else None
        return mime or "application/octet-stream"

    def attachment_kind(self):
        """image | pdf | video | audio | other | None"""
        self.ensure_one()
        if not self.attachment:
            return None
        mime = self.attachment_mimetype()
        if mime.startswith("image/"):
            return "image"
        if mime == "application/pdf":
            return "pdf"
        if mime.startswith("video/"):
            return "video"
        if mime.startswith("audio/"):
            return "audio"
        return "other"

    def media(self):
        """Material principal cargado por el docente, listo para la plantilla.

        Retorna dict {kind: iframe|video|image|pdf|audio, src} o {} si no hay nada visible."""
        self.ensure_one()
        kind, src = video_embed(self.video_url)
        if kind:
            return {"kind": kind, "src": src}
        akind = self.attachment_kind()
        if akind in ("image", "pdf", "video", "audio"):
            return {"kind": akind, "src": "/campus/leccion/%s/ver" % self.id}
        res = (self.resource_url or "").strip()
        low = res.lower().split("?")[0]
        if res and low.endswith(IMAGE_EXT):
            return {"kind": "image", "src": res}
        if res and low.endswith(".pdf"):
            return {"kind": "pdf", "src": res}
        if res and self.lesson_type == "video":
            kind, src = video_embed(res)
            if kind:
                return {"kind": kind, "src": src}
        return {}

    # ------------------------------------------------ material automático
    def _section_text_lessons(self):
        sec = self.section_id
        return sec.lesson_ids.filtered(
            lambda l: l.lesson_type in ("lectura", "caso", "laboratorio", "actividad")
            and len(html2plaintext(l.content or "")) > 120)

    @staticmethod
    def _blocks(html_content):
        """Divide un HTML en bloques (título, [puntos]) usando los <h4>/<h3> como cortes."""
        if not html_content or not html_content.strip():
            return []
        try:
            root = lxml_html.fragment_fromstring(html_content, create_parent="div")
        except Exception:  # noqa: BLE001
            return []
        blocks, cur = [], None
        for el in root.iterchildren():
            tag = el.tag if isinstance(el.tag, str) else ""
            text = re.sub(r"\s+", " ", el.text_content() or "").strip()
            if not text:
                continue
            if tag in ("h2", "h3", "h4", "h5"):
                cur = {"title": re.sub(r"^\d+[.)]\s*", "", text)[:90], "points": []}
                blocks.append(cur)
                continue
            if cur is None:
                cur = {"title": "", "points": []}
                blocks.append(cur)
            if tag in ("ul", "ol"):
                for li in el.iter("li"):
                    t = re.sub(r"\s+", " ", li.text_content() or "").strip()
                    if t:
                        cur["points"].append(t[:220])
            elif tag == "table":
                continue
            else:
                for sent in re.split(r"(?<=[.!?])\s+", text):
                    if len(sent) > 25:
                        cur["points"].append(sent[:220])
        return [b for b in blocks if b["points"]]

    def _key_blocks(self):
        blocks = []
        for l in self._section_text_lessons():
            blocks += self._blocks(l.content)
        if not blocks:
            blocks = self._blocks(self.section_id.course_id.description or "")
            blocks += self._blocks(self.section_id.course_id.outcomes or "")
        return blocks

    def infographic(self):
        """Datos para la infografía generada del núcleo."""
        self.ensure_one()
        sec = self.section_id
        gen = self.infographic_json if isinstance(self.infographic_json, dict) else {}
        if gen.get("terminos") or gen.get("puntos"):
            cert = sec.course_id.certification_id
            if gen.get("terminos"):
                pts = [{"title": str(p.get("termino") or "")[:40], "text": str(p.get("texto") or "")[:260],
                        "icon": visual.pick_icon(p.get("icono"), "%s %s" % (p.get("termino"), p.get("texto"))),
                        "label": str(p.get("etiqueta") or "")[:34]}
                       for p in gen["terminos"][:16] if isinstance(p, dict) and p.get("termino")]
            else:
                pts = [{"title": str(p.get("title") or "")[:90], "text": str(p.get("text") or "")[:260],
                        "icon": visual.pick_icon(p.get("icon"), str(p.get("title") or "")), "label": ""}
                       for p in gen["puntos"][:MAX_POINTS] if isinstance(p, dict) and p.get("title")]
            return {
                "title": gen.get("titulo") or sec.name,
                "objective": gen.get("pregunta_orientadora") or gen.get("objetivo") or sec.objective or "",
                "intro": gen.get("texto_orientador") or "",
                "key_fact": gen.get("dato_clave") or "",
                "points": pts,
                "route": [{"name": l.name, "type": l.lesson_type, "min": l.duration_min}
                          for l in sec.lesson_ids if l.id != self.id],
                "minutes": sum(sec.lesson_ids.mapped("duration_min")),
                "cert": cert and "%s · %s" % (cert.provider or "", cert.exam_code or cert.name) or "",
                "domains": cert.domain_ids.mapped("name")[:6] if cert else [],
            }
        blocks = [b for b in self._key_blocks() if b["title"]] or self._key_blocks()
        points = []
        for b in blocks[:MAX_POINTS]:
            t = b["title"] or (b["points"][0][:60] + "…")
            points.append({"title": t, "text": b["points"][0] if b["title"] else " ".join(b["points"][1:2]),
                           "icon": visual.pick_icon("", t), "label": ""})
        route = [{"name": l.name, "type": l.lesson_type, "min": l.duration_min}
                 for l in sec.lesson_ids if l.id != self.id]
        cert = sec.course_id.certification_id
        return {
            "key_fact": "", "intro": "",
            "title": sec.name, "objective": sec.objective or self.summary or "",
            "points": points, "route": route,
            "minutes": sum(sec.lesson_ids.mapped("duration_min")),
            "cert": cert and "%s · %s" % (cert.provider or "", cert.exam_code or cert.name) or "",
            "domains": cert.domain_ids.mapped("name")[:6] if cert else [],
        }

    def slides(self):
        """Diapositivas normalizadas (formato institucional): portada, contenido y cierre."""
        self.ensure_one()
        if isinstance(self.slides_json, list) and self.slides_json:
            out = deck_tools.normalize(self.slides_json)
            if out:
                return out
        sec = self.section_id
        course = sec.course_id
        is_intro = not self._section_text_lessons()
        meta = self.slide_meta()
        raw = [{"layout": "portada", "title": self.name if is_intro else (meta["section"] or sec.name),
                "subtitle": course.name if is_intro else (course.name or ""),
                "points": [p for p in [sec.objective or self.summary or course.subtitle or ""] if p]}]
        for b in self._key_blocks()[:8]:
            raw.append({"title": b["title"] or sec.name, "points": [_short(p) for p in b["points"][:4]]})
        if is_intro and course.certification_id:
            cert = course.certification_id
            raw.append({"layout": "tabla" if cert.domain_ids else "puntos", "title": "Tu meta: %s" % cert.name,
                        "subtitle": "%s · %s" % (cert.provider or "", cert.exam_code or ""), "icon": "objetivo",
                        "table": {"headers": ["Dominio del examen", "Peso"],
                                  "rows": [[d.name, "%s %%" % d.weight] for d in cert.domain_ids[:6]]},
                        "points": [d.name for d in cert.domain_ids[:5]]})
        nxt = [l.name for l in sec.lesson_ids if l.id != self.id][:5]
        raw.append({"layout": "cierre", "title": "Para continuar", "subtitle": "Actividades de esta sección",
                    "points": nxt or ["Pregúntale al tutor IA cualquier duda sobre este tema."], "icon": "cohete"})
        return deck_tools.normalize(raw)

    def slide_meta(self):
        self.ensure_one()
        sec = self.section_id
        m = re.match(r"(?i)\s*(n[úu]cleo\s+\d+)\s*[–-]?\s*(.*)", sec.name or "")
        return {"course": sec.course_id.name or "", "nucleo_label": (m.group(1).capitalize() if m else sec.name or ""),
                "section": (m.group(2) if m and m.group(2) else sec.name or ""),
                "program": "Tecnología en Desarrollo de Software y Aplicativos Móviles",
                "teacher": ", ".join(sec.course_id.teacher_ids.mapped("name")[:2])}

    def illustration(self, slide):
        return Markup(visual.illustration_svg(slide.get("icon"), slide.get("icon_label") or ""))

    def term_illustration(self, point):
        return Markup(visual.illustration_svg(point.get("icon"), point.get("label") or ""))

    def activity_questions(self):
        """Preguntas tipo caso de la actividad interactiva (sin revelar la respuesta en el HTML)."""
        self.ensure_one()
        out = []
        for i, q in enumerate(self.activity_json or []):
            if isinstance(q, dict) and q.get("enunciado") and q.get("opciones"):
                out.append({"n": i, "text": q["enunciado"], "options": [o.get("texto") for o in q["opciones"]]})
        return out

    def show_content(self):
        """Oculta el contenido si solo repite el resumen (evita texto duplicado)."""
        self.ensure_one()
        body = re.sub(r"\s+", " ", html2plaintext(self.content or "")).strip()
        if self.lesson_type not in ("video", "presentacion", "infografia", "quiz"):
            return bool(body)
        return bool(body) and body != (self.summary or "").strip()

    def needs_guide(self):
        """Lecturas/actividades casi vacías reciben una guía generada del curso."""
        self.ensure_one()
        return (self.lesson_type in ("lectura", "actividad")
                and len(html2plaintext(self.content or "").strip()) < 300 and not self.media())

    def narration(self, slide, index=0, total=1):
        """Texto que lee la voz: el guion del agente o uno conversacional armado a partir de los puntos."""
        return deck_tools.speakable(deck_tools.narration(slide, index, total))

    def youtube_search_url(self):
        q = self.video_query or "%s %s" % (self.summary or self.name, self.section_id.course_id.name)
        return "https://www.youtube.com/results?search_query=" + re.sub(r"\s+", "+", q.strip())

    # ------------------------------------------------------- cuestionarios
    def quiz_questions(self, n=5):
        """Preguntas de práctica del banco del curso (estables por lección)."""
        self.ensure_one()
        qs = self.course_id.question_ids.filtered(lambda q: len(q.option_ids) >= 2)
        own = qs.filtered(lambda q: q.section_id == self.section_id)
        if len(own) >= 3:
            qs = own
        if not qs:
            return qs
        ids = sorted(qs.ids)
        rnd = random.Random(self.id)
        pick = rnd.sample(ids, min(n, len(ids)))
        return self.env["campus.question"].browse(pick)

    # ------------------------------------------------------ archivos y voz
    def pptx_bytes(self):
        self.ensure_one()
        from ..tools import office
        return office.build_pptx(self.slides(), self.slide_meta())

    def voice_mp3(self, index):
        """MP3 de la narración de la diapositiva ``index`` (voz neuronal, guardado en caché)."""
        self.ensure_one()
        import base64
        import hashlib
        from ..tools import tts
        icp = self.env["ir.config_parameter"].sudo()
        if icp.get_param("campus_pi.tts_disabled") or not tts.available():
            return None
        slides = self.slides()
        if not 0 <= index < len(slides):
            return None
        text = self.narration(slides[index], index, len(slides))
        if not text:
            return None
        voice = icp.get_param("campus_pi.tts_voice") or tts.DEFAULT_VOICE
        rate = icp.get_param("campus_pi.tts_rate") or tts.DEFAULT_RATE
        key = hashlib.sha1(("%s|%s|%s" % (voice, rate, text)).encode()).hexdigest()
        Att = self.env["ir.attachment"].sudo()
        name = "campus_tts_%s.mp3" % key
        att = Att.search([("res_model", "=", "campus.lesson"), ("name", "=", name)], limit=1)
        if att:
            return base64.b64decode(att.datas)
        mp3 = tts.synthesize(text, voice, rate)
        Att.create({"name": name, "res_model": "campus.lesson", "res_id": self.id, "type": "binary",
                    "mimetype": "audio/mpeg", "datas": base64.b64encode(mp3)})
        return mp3


class CampusSectionKit(models.Model):
    _inherit = "campus.section"

    def _kit(self):
        self.ensure_one()
        kit = dict(self.kit_json or {}) if isinstance(self.kit_json, dict) else {}
        les = self.lesson_ids
        if not kit.get("infografia"):
            ig = les.filtered(lambda l: l.lesson_type == "infografia")[:1]
            kit["infografia"] = ig.infographic_json if ig and isinstance(ig.infographic_json, dict) else {}
            if ig and not kit["infografia"]:
                data = ig.infographic()
                kit["infografia"] = {"titulo": data["title"], "pregunta_orientadora": data["objective"],
                                     "terminos": [{"termino": p["title"], "texto": p["text"], "icono": p["icon"]}
                                                  for p in data["points"]]}
        if not kit.get("lectura"):
            lec = les.filtered(lambda l: l.lesson_type == "lectura")[:1]
            kit["lectura"] = {"titulo": lec.name or self.name, "secciones_html": lec.content or ""}
        return kit

    def package_files(self):
        """[(nombre, bytes)] con los formatos institucionales del núcleo (Word + PowerPoint)."""
        self.ensure_one()
        from ..tools import office, tts
        les = self.lesson_ids
        deck_l = les.filtered(lambda l: l.lesson_type in ("video", "presentacion") and l.slides_json)[:1] or \
            les.filtered(lambda l: l.lesson_type in ("video", "presentacion"))[:1]
        kit = self._kit()
        anchor = deck_l or les[:1]
        meta = anchor.slide_meta() if anchor else {"course": self.course_id.name, "section": self.name}
        m = re.search(r"\d+", meta.get("nucleo_label") or "")
        meta.update({"nucleo_num": m.group(0) if m else "", "objective": self.objective or "",
                     "credits": 3,
                     "voice": dict(tts.VOICES).get(self.env["ir.config_parameter"].sudo().get_param("campus_pi.tts_voice")
                                                   or tts.DEFAULT_VOICE, "voz neuronal")})
        n = meta.get("nucleo_num") or ""
        tag = "N%s" % n if n else re.sub(r"\W+", "_", self.name)[:20]
        slides = deck_l.slides() if deck_l else []
        files = []
        if kit.get("bibliografia"):
            files.append(("5. Recursos bibliográficos %s.docx" % tag, office.docx_bibliografia(kit, meta)))
        files.append(("5.1 Lectura %s.docx" % tag, office.docx_lectura(kit, meta)))
        if slides:
            files.append(("6. Guion del video explicativo %s.docx" % tag, office.docx_guion(slides, meta)))
            files.append(("6.1 Presentación %s.pptx" % tag, office.build_pptx(slides, meta)))
        act = kit.get("actividad") or {}
        act_l = les.filtered(lambda l: l.lesson_type == "actividad" and l.activity_json)[:1]
        if act_l and not act.get("preguntas"):
            act = dict(act, preguntas=act_l.activity_json, titulo=act.get("titulo") or act_l.name)
        if act.get("preguntas"):
            files.append(("7. Actividad formativa H5P %s.docx" % tag, office.docx_actividad(act, slides, meta)))
        if kit.get("infografia"):
            files.append(("8. Infografía %s.docx" % tag, office.docx_infografia(kit["infografia"], meta)))
        if kit.get("caso"):
            files.append(("11. Caso integrador %s (con rúbrica).docx" % tag, office.docx_caso(kit["caso"], meta)))
        return files

    def package_zip(self):
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in self.package_files():
                z.writestr(name, data)
        return buf.getvalue()
