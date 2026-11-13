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

from odoo import models
from odoo.tools import html2plaintext

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
        blocks = [b for b in self._key_blocks() if b["title"]] or self._key_blocks()
        points = []
        for b in blocks[:MAX_POINTS]:
            points.append({"title": b["title"] or (b["points"][0][:60] + "…"),
                           "text": b["points"][0] if b["title"] else " ".join(b["points"][1:2])})
        route = [{"name": l.name, "type": l.lesson_type, "min": l.duration_min}
                 for l in sec.lesson_ids if l.id != self.id]
        cert = sec.course_id.certification_id
        return {
            "title": sec.name, "objective": sec.objective or self.summary or "",
            "points": points, "route": route,
            "minutes": sum(sec.lesson_ids.mapped("duration_min")),
            "cert": cert and "%s · %s" % (cert.provider or "", cert.exam_code or cert.name) or "",
            "domains": cert.domain_ids.mapped("name")[:6] if cert else [],
        }

    def slides(self):
        """Diapositivas generadas: portada, una por bloque de contenido y cierre."""
        self.ensure_one()
        sec = self.section_id
        course = sec.course_id
        is_intro = not self._section_text_lessons()
        out = [{"title": self.name, "lead": sec.name if not is_intro else course.name,
                "points": [p for p in [sec.objective or self.summary or course.subtitle or ""] if p]}]
        for b in self._key_blocks()[:8]:
            out.append({"title": b["title"] or sec.name, "lead": "", "points": b["points"][:5]})
        if is_intro and course.certification_id:
            cert = course.certification_id
            out.append({"title": "Tu meta: %s" % cert.name, "lead": "%s · %s" % (cert.provider or "", cert.exam_code or ""),
                        "points": ["%s (%s %%)" % (d.name, d.weight) for d in cert.domain_ids[:6]]})
        nxt = [l.name for l in sec.lesson_ids if l.id != self.id][:5]
        out.append({"title": "Para continuar", "lead": "Actividades de esta sección",
                    "points": nxt or ["Pregúntale al tutor IA cualquier duda sobre este tema."]})
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

    def narration(self, slide):
        txt = " ".join([slide.get("title") or "", slide.get("lead") or ""] + list(slide.get("points") or []))
        return re.sub(r"\s+", " ", txt).strip()

    def youtube_search_url(self):
        q = "%s %s" % (self.summary or self.name, self.section_id.course_id.name)
        return "https://www.youtube.com/results?search_query=" + re.sub(r"\s+", "+", q.strip())

    # ------------------------------------------------------- cuestionarios
    def quiz_questions(self, n=5):
        """Preguntas de práctica del banco del curso (estables por lección)."""
        self.ensure_one()
        qs = self.course_id.question_ids.filtered(lambda q: len(q.option_ids) >= 2)
        if not qs:
            return qs
        ids = sorted(qs.ids)
        rnd = random.Random(self.id)
        pick = rnd.sample(ids, min(n, len(ids)))
        return self.env["campus.question"].browse(pick)
