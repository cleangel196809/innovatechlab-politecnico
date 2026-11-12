# -*- coding: utf-8 -*-
"""Agentes de IA del campus (Anthropic Claude).

1. Agente de diseño instruccional: syllabus -> curso completo (núcleos, lecciones,
   sesiones virtuales y presenciales asistidas, banco de preguntas del simulador).
2. Agente tutor: responde dudas con el contexto del curso (lecciones + syllabus +
   dominios de la certificación) y prepara planes de estudio personalizados.

Sin API key el campus sigue funcionando en "modo sin IA" (generación heurística),
para que la demo nunca se caiga.
"""
import base64
import io
import json
import logging
import os
import re
import zipfile
from datetime import datetime, time, timedelta
from xml.etree import ElementTree

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import html2plaintext, html_escape

_logger = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-5"
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class CampusAiAgent(models.AbstractModel):
    _name = "campus.ai.agent"
    _description = "Agentes de IA del campus"

    # ------------------------------------------------------------------ LLM
    @api.model
    def _api_key(self):
        return (os.environ.get("ANTHROPIC_API_KEY")
                or self.env["ir.config_parameter"].sudo().get_param("campus_pi.anthropic_api_key") or "")

    @api.model
    def is_enabled(self):
        # Sólo se considera válida una clave real de Anthropic (evita fallos con "pendiente", etc.)
        return self._api_key().strip().startswith("sk-ant-")

    @api.model
    def _call(self, system, messages, max_tokens=2000, temperature=0.4):
        key = self._api_key()
        if not key:
            raise UserError(_("No hay API key de Anthropic configurada."))
        model = (self.env["ir.config_parameter"].sudo().get_param("campus_pi.claude_model")
                 or DEFAULT_MODEL)
        resp = requests.post(
            API_URL,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": model, "max_tokens": max_tokens, "temperature": temperature,
                  "system": system, "messages": messages},
            timeout=120,
        )
        if resp.status_code >= 400:
            _logger.error("Anthropic API %s: %s", resp.status_code, resp.text[:500])
            raise UserError(_("Error del proveedor de IA (%s): %s") % (resp.status_code, resp.text[:300]))
        data = resp.json()
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")

    @api.model
    def _json(self, text):
        text = text.strip()
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
        start = min([i for i in (text.find("{"), text.find("[")) if i >= 0] or [0])
        end = max(text.rfind("}"), text.rfind("]"))
        return json.loads(text[start:end + 1])

    # ------------------------------------------------------- texto syllabus
    @api.model
    def extract_text(self, data_b64, filename):
        raw = base64.b64decode(data_b64 or b"")
        name = (filename or "").lower()
        try:
            if name.endswith(".docx"):
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    root = ElementTree.fromstring(z.read("word/document.xml"))
                lines = []
                for p in root.iter(W_NS + "p"):
                    t = "".join(n.text or "" for n in p.iter(W_NS + "t")).strip()
                    if t:
                        lines.append(t)
                return "\n".join(lines)
            if name.endswith(".pdf"):
                from odoo.tools.pdf import PdfFileReader
                reader = PdfFileReader(io.BytesIO(raw), strict=False)
                return "\n".join((reader.getPage(i).extractText() or "") for i in range(reader.getNumPages()))
            return raw.decode("utf-8", errors="ignore")
        except Exception as e:  # noqa: BLE001
            _logger.exception("No se pudo leer el syllabus")
            raise UserError(_("No se pudo leer el archivo %s: %s") % (filename, e))

    # ---------------------------------------- agente de diseño instruccional
    COURSE_SYSTEM = """Eres el Agente de Diseño Instruccional de InnobaTech Lab del Politécnico Internacional (Colombia).
Conviertes un syllabus institucional (formato PI-GA-FT-141) en un curso virtual de microcertificación
alineado con una certificación internacional. Respetas la estructura institucional: sección "Inicio",
Núcleos 1..N y "Cierre". En cada núcleo combinas: lectura, presentación interactiva o video, infografía,
actividad formativa, una sesión sincrónica virtual y una sesión presencial asistida por IA (con guion
para el agente: agenda, preguntas detonantes, reto práctico y cierre), y el cuestionario del núcleo.
Escribes en español de Colombia, claro y profesional. Respondes SOLO con JSON válido, sin texto extra."""

    COURSE_SCHEMA = """{
 "name": str, "subtitle": str, "description_html": str, "outcomes_html": str, "skills": "a, b, c",
 "level": "basico|intermedio|avanzado", "hours": int,
 "sections": [{"name": "Inicio|Núcleo 1 – ...|Cierre", "objective": str,
   "lessons": [{"name": str, "type": "lectura|video|presentacion|infografia|actividad|caso|quiz|sesion_virtual|sesion_presencial|laboratorio",
                "summary": str, "duration_min": int, "content_html": str, "ai_guide_html": str}]}],
 "questions": [{"domain": str, "question": str, "explanation": str,
   "options": [{"text": str, "correct": bool, "feedback": str}]}]
}"""

    @api.model
    def generate_course(self, vals):
        """vals: name, syllabus_text, certification_id, date_start, date_end, modality,
        teacher_ids, student_ids, syllabus_file, syllabus_filename, instructions"""
        cert = self.env["campus.certification"].browse(vals.get("certification_id") or [])
        if self.is_enabled():
            data, log = self._generate_with_llm(vals, cert), "Generado con Claude a partir del syllabus."
        else:
            data, log = self._generate_heuristic(vals, cert), (
                "Modo sin IA: estructura generada por reglas a partir del syllabus. "
                "Configure ANTHROPIC_API_KEY para contenido completo.")
        return self._create_course(data, vals, cert, log)

    def _generate_with_llm(self, vals, cert):
        cert_txt = "Ninguna"
        if cert:
            cert_txt = "%s (%s, examen %s). Dominios: %s" % (
                cert.name, cert.provider, cert.exam_code or "-",
                "; ".join("%s %s%%" % (d.name, d.weight) for d in cert.domain_ids))
        prompt = (
            "Nombre sugerido del curso: %s\nModalidad: %s\nCertificación internacional objetivo: %s\n"
            "Instrucciones del administrador: %s\n\nGenera 3 a 5 lecciones por núcleo, contenido_html de "
            "150-300 palabras por lección (con subtítulos <h4> y listas), y 12 preguntas de opción múltiple "
            "tipo caso para el simulador, distribuidas según los dominios de la certificación.\n"
            "Esquema JSON exacto:\n%s\n\nSYLLABUS:\n%s"
        ) % (vals.get("name") or "", vals.get("modality") or "virtual", cert_txt,
             vals.get("instructions") or "-", self.COURSE_SCHEMA, (vals.get("syllabus_text") or "")[:60000])
        text = self._call(self.COURSE_SYSTEM, [{"role": "user", "content": prompt}], max_tokens=16000)
        return self._json(text)

    def _generate_heuristic(self, vals, cert):
        text = vals.get("syllabus_text") or ""
        nucleos = []
        for m in re.finditer(r"N[úu]cleo\s+(\d)\s*[–\-:]\s*([^\n.]{3,90})\.?\s*([^\n]{0,400})", text):
            num = int(m.group(1))
            if num not in [n[0] for n in nucleos]:
                nucleos.append((num, m.group(2).strip(), m.group(3).strip()))
        if not nucleos:
            nucleos = [(i, "Unidad %s" % i, "") for i in range(1, 5)]
        nucleos.sort()
        desc = ""
        m = re.search(r"DESCRIPCI[ÓO]N DEL CURSO\s*\n(.{50,1500}?)\n", text, re.S)
        if m:
            desc = m.group(1)
        sections = [{"name": "Inicio", "objective": "Bienvenida, guía del estudiante y diagnóstico inicial.",
                     "lessons": [
                         {"name": "Video de bienvenida", "type": "video", "duration_min": 10},
                         {"name": "Guía del estudiante y syllabus", "type": "lectura", "duration_min": 20},
                         {"name": "Cuestionario diagnóstico inicial", "type": "quiz", "duration_min": 20}]}]
        for num, title, obj in nucleos:
            sections.append({"name": "Núcleo %s – %s" % (num, title), "objective": obj, "lessons": [
                {"name": "Lectura: %s" % title, "type": "lectura", "duration_min": 45},
                {"name": "Presentación interactiva", "type": "presentacion", "duration_min": 30},
                {"name": "Infografía del núcleo", "type": "infografia", "duration_min": 10},
                {"name": "Sesión sincrónica virtual", "type": "sesion_virtual", "duration_min": 90},
                {"name": "Sesión presencial asistida por IA", "type": "sesion_presencial", "duration_min": 120},
                {"name": "Cuestionario Núcleo %s" % num, "type": "quiz", "duration_min": 30}]})
        sections.append({"name": "Cierre", "objective": "Autoevaluación, diagnóstico final y simulacro.",
                         "lessons": [{"name": "Autoevaluación", "type": "actividad", "duration_min": 20},
                                     {"name": "Simulacro de certificación", "type": "quiz", "duration_min": 60}]})
        return {"name": vals.get("name"), "description_html": "<p>%s</p>" % html_escape(desc),
                "sections": sections, "questions": []}

    def _create_course(self, data, vals, cert, log):
        d0 = fields.Date.to_date(vals.get("date_start")) or fields.Date.context_today(self)
        d1 = fields.Date.to_date(vals.get("date_end")) or (d0 + timedelta(weeks=8))
        sections = data.get("sections") or []
        span = max((d1 - d0).days, len(sections) or 1)
        step = span // max(len(sections), 1)
        course = self.env["campus.course"].sudo().create({
            "name": vals.get("name") or data.get("name") or "Curso",
            "subtitle": data.get("subtitle"),
            "description": data.get("description_html"),
            "outcomes": data.get("outcomes_html"),
            "skills": data.get("skills"),
            "level": data.get("level") if data.get("level") in ("basico", "intermedio", "avanzado") else "intermedio",
            "hours": data.get("hours") or 144,
            "modality": vals.get("modality") or "virtual",
            "date_start": d0, "date_end": d1,
            "certification_id": cert.id or False,
            "teacher_ids": [(6, 0, vals.get("teacher_ids") or [])],
            "syllabus_file": vals.get("syllabus_file"),
            "syllabus_filename": vals.get("syllabus_filename"),
            "syllabus_text": (vals.get("syllabus_text") or "")[:100000],
            "ai_generated": True, "ai_log": log, "state": "draft",
        })
        valid_types = dict(self.env["campus.lesson"]._fields["lesson_type"].selection)
        for i, s in enumerate(sections):
            s_start = d0 + timedelta(days=i * step)
            sec = self.env["campus.section"].sudo().create({
                "course_id": course.id, "sequence": i, "name": s.get("name") or "Sección %s" % i,
                "objective": s.get("objective"), "date_start": s_start,
                "date_end": min(s_start + timedelta(days=max(step - 1, 0)), d1)})
            for j, ls in enumerate(s.get("lessons") or []):
                ltype = ls.get("type") if ls.get("type") in valid_types else "lectura"
                session_dt = False
                if ltype == "sesion_virtual":   # 7:00 p. m. hora Colombia (UTC-5)
                    session_dt = datetime.combine(s_start + timedelta(days=1), time(0, 0))
                elif ltype == "sesion_presencial":  # sábado siguiente 8:00 a. m. Colombia
                    sat = s_start + timedelta(days=(5 - s_start.weekday()) % 7)
                    session_dt = datetime.combine(sat, time(13, 0))
                self.env["campus.lesson"].sudo().create({
                    "section_id": sec.id, "sequence": j, "name": ls.get("name") or "Lección",
                    "lesson_type": ltype, "summary": ls.get("summary"),
                    "duration_min": ls.get("duration_min") or 30,
                    "content": ls.get("content_html") or "<p>Contenido pendiente: el docente puede "
                               "completarlo o pedir al agente que lo redacte.</p>",
                    "ai_guide": ls.get("ai_guide_html"), "session_datetime": session_dt})
        self._create_questions(course, data.get("questions") or [])
        if vals.get("student_ids"):
            course.enroll_users(self.env["res.users"].browse(vals["student_ids"]))
        return course

    def _create_questions(self, course, questions, source="ai"):
        Q = self.env["campus.question"].sudo()
        for q in questions:
            opts = q.get("options") or []
            if not q.get("question") or len(opts) < 2:
                continue
            Q.create({"course_id": course.id, "domain": q.get("domain") or "General",
                      "name": q["question"], "explanation": q.get("explanation"), "source": source,
                      "option_ids": [(0, 0, {"sequence": k, "name": o.get("text") or "-",
                                             "is_correct": bool(o.get("correct")),
                                             "feedback": o.get("feedback")}) for k, o in enumerate(opts)]})

    @api.model
    def generate_questions(self, course, n=10):
        if not self.is_enabled():
            raise UserError(_("Configure la API key de Anthropic para generar preguntas."))
        cert = course.certification_id
        lessons = "\n".join("- %s: %s" % (l.name, l.summary or "") for l in course.lesson_ids[:60])
        prompt = ("Genera %s preguntas de opción múltiple (4 opciones, 1 correcta) tipo caso, estilo examen "
                  "%s, para el curso '%s'. Dominios: %s.\nLecciones:\n%s\n"
                  "Responde SOLO un JSON: [{\"domain\":str,\"question\":str,\"explanation\":str,"
                  "\"options\":[{\"text\":str,\"correct\":bool,\"feedback\":str}]}]") % (
            n, cert.name or "de certificación", course.name,
            ", ".join(cert.domain_ids.mapped("name")) or "General", lessons)
        data = self._json(self._call(self.COURSE_SYSTEM, [{"role": "user", "content": prompt}], 8000))
        self._create_questions(course, data if isinstance(data, list) else data.get("questions", []))
        return True

    # ------------------------------------------------------------ tutor IA
    def _course_context(self, course):
        cert = course.certification_id
        parts = ["CURSO: %s (%s)" % (course.name, course.subtitle or "")]
        if cert:
            parts.append("CERTIFICACIÓN OBJETIVO: %s – %s %s. Dominios: %s" % (
                cert.provider, cert.name, cert.exam_code or "",
                "; ".join("%s (%s%%)" % (d.name, d.weight) for d in cert.domain_ids)))
        for sec in course.section_ids:
            parts.append("\n## %s" % sec.name)
            for l in sec.lesson_ids:
                body = html2plaintext(l.content or "")[:900]
                parts.append("- [%s] %s: %s" % (l.lesson_type, l.name, body))
        return "\n".join(parts)[:45000]

    def _weak_domains(self, enrollment):
        last = enrollment.attempt_ids.filtered(lambda a: a.state == "done")[:1]
        if not last or not last.domain_report:
            return []
        return sorted(last.domain_report.items(), key=lambda kv: kv[1].get("pct", 0))[:3]

    @api.model
    def tutor_reply(self, course, user, message):
        Msg = self.env["campus.ai.message"].sudo()
        Msg.create({"user_id": user.id, "course_id": course.id, "role": "user", "content": message})
        enrollment = course.enrollment_ids.filtered(lambda e: e.user_id == user)[:1]
        if not self.is_enabled():
            answer = self._offline_answer(course, message)
        else:
            weak = self._weak_domains(enrollment) if enrollment else []
            system = (
                "Eres el Tutor IA de InnobaTech Lab (Politécnico Internacional). Acompañas a %s en el curso. "
                "Método socrático: primero pregunta qué ha intentado, explica con ejemplos colombianos "
                "cotidianos, referencia la lección exacta del curso y termina con una pregunta de verificación "
                "o un mini-reto. Nunca entregues resuelto un entregable calificable; guía paso a paso. "
                "Si preguntan por el examen internacional, relaciona el tema con su dominio y peso. "
                "Responde en español, máximo 250 palabras, con formato Markdown sencillo.\n"
                "Dominios más débiles del estudiante en su último simulacro: %s\n\nCONTEXTO DEL CURSO:\n%s"
                "\n\nINSTRUCCIONES DEL DOCENTE: %s") % (
                user.name, ", ".join("%s (%s%%)" % (d, r.get("pct")) for d, r in weak) or "sin datos",
                self._course_context(course), course.tutor_prompt or "-")
            history = Msg.search([("user_id", "=", user.id), ("course_id", "=", course.id)],
                                 order="id desc", limit=12)
            msgs = [{"role": m.role, "content": m.content} for m in reversed(history)]
            try:
                answer = self._call(system, msgs, max_tokens=900)
            except UserError as e:
                answer = "⚠️ El tutor IA no está disponible en este momento (%s). " % e.args[0][:120] + \
                         self._offline_answer(course, message)
        Msg.create({"user_id": user.id, "course_id": course.id, "role": "assistant", "content": answer})
        return answer

    def _offline_answer(self, course, message):
        words = {w for w in re.findall(r"\w{5,}", (message or "").lower())}
        scored = []
        for l in course.lesson_ids:
            txt = (l.name + " " + html2plaintext(l.content or "")).lower()
            score = sum(1 for w in words if w in txt)
            if score:
                scored.append((score, l))
        scored.sort(key=lambda x: -x[0])
        if not scored:
            return ("(Modo sin IA) No encontré una lección relacionada. Agenda una tutoría virtual con tu "
                    "docente o revisa el núcleo correspondiente.")
        tips = "\n".join("- **%s** (%s)" % (l.name, l.section_id.name) for _s, l in scored[:3])
        return "(Modo sin IA) Te recomiendo repasar estas lecciones:\n%s" % tips

    @api.model
    def prepare_tutoring_plan(self, tutoring):
        enrollment = tutoring.course_id.enrollment_ids.filtered(lambda e: e.user_id == tutoring.student_id)[:1]
        weak = self._weak_domains(enrollment) if enrollment else []
        weak_txt = ", ".join("%s (%s%%)" % (d, r.get("pct")) for d, r in weak) or "sin simulacros aún"
        if not self.is_enabled():
            return ("<p><b>Plan base (modo sin IA)</b></p><ul><li>Tema solicitado: %s</li>"
                    "<li>Dominios a reforzar: %s</li><li>Repasa las lecciones del núcleo y presenta un "
                    "simulacro antes de la sesión.</li></ul>") % (html_escape(tutoring.name), html_escape(weak_txt))
        prompt = ("Prepara un plan de tutoría de %s minutos para el tema '%s'. Dudas del estudiante: %s. "
                  "Dominios débiles: %s. Devuelve HTML simple (h4, ul, li, p): objetivo, diagnóstico rápido "
                  "(3 preguntas), explicación guiada, ejercicio práctico, preguntas tipo examen y tarea.") % (
            tutoring.duration_min, tutoring.name, tutoring.notes or "-", weak_txt)
        system = "Eres el Tutor IA del Politécnico Internacional.\nCONTEXTO:\n" + self._course_context(tutoring.course_id)
        try:
            return self._call(system, [{"role": "user", "content": prompt}], max_tokens=1800)
        except UserError as e:
            return "<p>No fue posible generar el plan: %s</p>" % html_escape(e.args[0][:200])
