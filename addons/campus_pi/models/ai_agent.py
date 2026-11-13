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


def call_messages(conf, system, messages, max_tokens=2000, temperature=0.4, tools=None, timeout=300):
    """Llama a la API de mensajes de Anthropic. Devuelve (texto, fuentes, stop_reason).

    Con ``tools`` (p. ej. búsqueda web del servidor) continúa los turnos en pausa
    (``pause_turn``) y recoge las URL consultadas y citadas como fuentes.
    No usa el ORM: puede ejecutarse en hilos paralelos."""

    key = conf.get("key")
    if not key:
        raise UserError("No hay API key de Anthropic configurada.")
    payload = {"model": conf.get("model") or DEFAULT_MODEL, "max_tokens": max_tokens, "system": system,
               "messages": list(messages)}
    if tools:
        payload["tools"] = tools
    else:
        payload["temperature"] = temperature
    texts, sources, stop = [], [], None
    for _turn in range(5):
        try:
            resp = requests.post(
                conf.get("url") or API_URL, json=payload, timeout=timeout,
                headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"})
        except requests.RequestException as e:
            raise UserError("No fue posible contactar al proveedor de IA: %s" % e)
        if resp.status_code >= 400:
            _logger.error("Anthropic API %s: %s", resp.status_code, resp.text[:500])
            raise UserError("Error del proveedor de IA (%s): %s" % (resp.status_code, resp.text[:300]))
        data = resp.json()
        stop = data.get("stop_reason")
        for b in data.get("content", []):
            if b.get("type") == "text":
                texts.append(b.get("text", ""))
                for c in b.get("citations") or []:
                    if c.get("url"):
                        sources.append({"title": c.get("title") or c["url"], "url": c["url"]})
            elif b.get("type") == "web_search_tool_result" and isinstance(b.get("content"), list):
                for r in b["content"]:
                    if r.get("url"):
                        sources.append({"title": r.get("title") or r["url"], "url": r["url"],
                                        "searched": True})
        if stop != "pause_turn":
            break
        payload["messages"] = payload["messages"] + [{"role": "assistant", "content": data.get("content", [])}]
    seen, uniq = set(), []
    for src in sources:
        if src["url"] not in seen:
            seen.add(src["url"])
            uniq.append(src)
    return "".join(texts), uniq, stop


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
    def _api_url(self):
        return (os.environ.get("CAMPUS_ANTHROPIC_URL")
                or self.env["ir.config_parameter"].sudo().get_param("campus_pi.anthropic_url") or API_URL)

    @api.model
    def _model(self):
        return (self.env["ir.config_parameter"].sudo().get_param("campus_pi.claude_model") or DEFAULT_MODEL)

    @api.model
    def _llm_conf(self):
        """Configuración para llamar al modelo sin tocar la base de datos (apto para hilos)."""
        return {"key": self._api_key(), "url": self._api_url(), "model": self._model()}

    @api.model
    def _messages(self, system, messages, max_tokens=2000, temperature=0.4, tools=None, timeout=300):
        return call_messages(self._llm_conf(), system, messages, max_tokens, temperature, tools, timeout)

    @api.model
    def _call(self, system, messages, max_tokens=2000, temperature=0.4):
        return self._messages(system, messages, max_tokens=max_tokens, temperature=temperature)[0]

    @api.model
    def _json(self, text):
        text = (text or "").strip()
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
        start = min([i for i in (text.find("{"), text.find("[")) if i >= 0] or [0])
        end = max(text.rfind("}"), text.rfind("]"))
        chunk = text[start:end + 1]
        try:
            return json.loads(chunk)
        except ValueError:
            # Las comas finales son el error más común del modelo
            fixed = re.sub(r",\s*([}\]])", r"\1", chunk)
            return json.loads(fixed)

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
    COURSE_SYSTEM = """Eres el Agente de Diseño Instruccional de InnovaTech Lab del Politécnico Internacional (Colombia).
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
        """Compatibilidad: ejecuta el agente por etapas de forma síncrona y devuelve el curso."""
        job = self.env["campus.agent.job"].sudo().create({
            "name": vals.get("name") or "Curso", "syllabus_file": vals.get("syllabus_file"),
            "syllabus_filename": vals.get("syllabus_filename") or "syllabus.txt",
            "certification_id": vals.get("certification_id") or False,
            "deep_research": vals.get("deep_research", True),
            "params": {k: v for k, v in vals.items() if k not in ("syllabus_file", "syllabus_text")},
        })
        if not job.syllabus_file and vals.get("syllabus_text"):
            job.write({"syllabus_file": base64.b64encode(vals["syllabus_text"].encode()),
                       "syllabus_filename": "syllabus.txt"})
        job.action_start(background=False)
        if job.state == "error":
            raise UserError(job.error)
        return job.course_id

    STRUCTURE_SYSTEM = """Extraes la estructura de un syllabus institucional del Politécnico Internacional (formato
PI-GA-FT-141) a partir de texto mal formateado (PDF o texto plano). No inventas: si un dato no aparece, déjalo vacío.
Respondes SOLO con JSON válido."""

    @api.model
    def structure_syllabus(self, text):
        prompt = ("Extrae del syllabus: asignatura, resultado de aprendizaje, competencias, producto, objetivos (3.4.x) y "
                  "la tabla de ALINEACIÓN CURRICULAR: por núcleo su número, título, temas (lista), objetivo, "
                  "estrategias (lista) y criterios de evaluación (lista); y la tabla de CRITERIOS DE EVALUACIÓN "
                  "(cuándo e instrumento). Esquema: {\"asignatura\": str, \"resultado_aprendizaje\": str, "
                  "\"competencias\": str, \"producto\": str, \"objetivos\": [str], \"nucleos\": [{\"numero\": int, "
                  "\"titulo\": str, \"temas\": [str], \"objetivo\": str, \"estrategias\": [str], \"criterios\": [str]}], "
                  "\"evaluacion\": [{\"cuando\": str, \"instrumento\": str, \"evidencia\": str}]}\n\nTEXTO:\n%s") % (text or "")[:60000]
        data = self._json(self._call(self.STRUCTURE_SYSTEM, [{"role": "user", "content": prompt}], 6000, 0.0))
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------- investigación web
    RESEARCH_SYSTEM = """Eres el Agente Investigador de InnovaTech Lab (Politécnico Internacional, Colombia).
Antes de diseñar un curso verificas en fuentes oficiales y actuales la información que el syllabus no garantiza:
la certificación internacional pertinente (versión vigente, código, dominios y pesos, formato, precio),
novedades 2025-2026 de cada núcleo y recursos abiertos de calidad (documentación oficial, estándares, cursos
gratuitos; en español cuando existan). Usa la herramienta de búsqueda web; no inventes datos: si algo no se
puede verificar, dilo en "advertencias". Respondes SOLO con JSON válido."""

    @api.model
    def research_course(self, syl, cert=None, instructions=None):
        from ..tools import syllabus as syl_tools
        from .agent_job import RESEARCH_SCHEMA
        hint = ("La certificación elegida por el administrador es %s (%s %s). Verifica si sigue vigente o si hay "
                "una versión más reciente." % (cert.name, cert.provider, cert.exam_code or "")) if cert else (
                "Identifica la certificación internacional más pertinente para este syllabus (si el syllabus "
                "nombra una, verifica esa).")
        prompt = ("Fecha de hoy: %s.\n%s\nInstrucciones del administrador: %s\n\nSYLLABUS:\n%s\n\n"
                  "Para cada núcleo (por número) da 2-4 novedades vigentes, 4-6 conceptos clave y 2-4 recursos "
                  "con URL real. Esquema JSON exacto:\n%s") % (
            fields.Date.today(), hint, instructions or "-", syl_tools.summary(syl, 9000), RESEARCH_SCHEMA)
        tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}]
        text, sources, _stop = self._messages(self.RESEARCH_SYSTEM, [{"role": "user", "content": prompt}],
                                              max_tokens=8000, tools=tools, timeout=420)
        data = self._json(text)
        if not isinstance(data, dict):
            data = {}
        data["_sources"] = sources
        return data

    # ----------------------------------------------- contenido por núcleo
    NUCLEO_SYSTEM = """Eres el Agente de Diseño Instruccional de InnovaTech Lab del Politécnico Internacional (Colombia).
Desarrollas el contenido completo de UN núcleo de un curso virtual a partir del syllabus institucional
(PI-GA-FT-141), respetando su objetivo, temas, estrategias y criterios de evaluación, y alineándolo con la
certificación internacional objetivo y con la investigación verificada que se te entrega. Escribes en español
de Colombia, claro, riguroso y con ejemplos de organizaciones colombianas. Citas las fuentes de la investigación
con enlaces <a href> en la lectura. Nunca inventas URL: usa solo las de la investigación o del syllabus.
Respondes SOLO con JSON válido, sin texto adicional."""

    @api.model
    def nucleo_content_payload(self, summary, nuc, cert_info, research, instructions=None, conf=None):
        """Genera el contenido de un núcleo. No usa la base de datos si se pasa ``conf``."""
        from .agent_job import NUCLEO_SCHEMA
        conf = conf or self._llm_conf()
        rn = next((x for x in (research or {}).get("nucleos") or [] if x.get("numero") == nuc["numero"]), {})
        cert_txt = "Ninguna"
        if cert_info:
            cert_txt = "%s (%s, %s). Dominios: %s" % (cert_info["name"], cert_info["provider"], cert_info["code"],
                                                       "; ".join("%s %s%%" % d for d in cert_info["domains"]))
        prompt = (
            "NÚCLEO %s – %s\nObjetivo: %s\nTemas: %s\nEstrategias: %s\nCriterios de evaluación: %s\n\n"
            "CERTIFICACIÓN: %s\nINVESTIGACIÓN VERIFICADA PARA ESTE NÚCLEO: %s\n"
            "INSTRUCCIONES DEL ADMINISTRADOR: %s\n\nSYLLABUS COMPLETO (contexto):\n%s\n\n"
            "Requisitos: lectura de 900-1300 palabras con <h4>, <ul>, ejemplos y una sección final «Fuentes» con "
            "enlaces; presentación de 7-9 diapositivas (3-5 puntos cada una); infografía de 5-6 puntos; guion del "
            "video de 3-5 minutos y una búsqueda de YouTube en español; actividad formativa; laboratorio práctico "
            "con pasos (o null si el núcleo no lo admite); evaluación según los criterios del syllabus con "
            "instrucciones, entregables y rúbrica en tabla (BUENO/REGULAR/INSUFICIENTE); agenda de la sesión "
            "virtual de 90 min; guion del agente IA para la sesión presencial (diagnóstico, preguntas "
            "detonantes, reto práctico, cierre); 6 preguntas tipo examen de opción múltiple (4 opciones, 1 "
            "correcta, retroalimentación por opción) con el nombre exacto del dominio de la certificación.\n"
            "Esquema JSON exacto:\n%s") % (
            nuc["numero"], nuc["titulo"], nuc.get("objetivo") or "-", "; ".join(nuc.get("temas") or []) or "-",
            "; ".join(nuc.get("estrategias") or []) or "-", " ".join(nuc.get("criterios") or []) or "-",
            cert_txt, json.dumps(rn, ensure_ascii=False)[:5000] or "-", instructions or "-", summary[:9000],
            NUCLEO_SCHEMA)
        last = None
        for attempt in range(2):
            msgs = [{"role": "user", "content": prompt + (
                "\n\nIMPORTANTE: la respuesta anterior no fue JSON válido o quedó incompleta; sé más conciso "
                "(lectura de máximo 800 palabras)." if attempt else "")}]
            text, _src, stop = call_messages(conf, self.NUCLEO_SYSTEM, msgs, max_tokens=16000, temperature=0.5,
                                             timeout=600)
            try:
                data = self._json(text)
                if isinstance(data, dict) and data.get("lectura"):
                    return data
            except ValueError as e:
                last = e
        raise UserError("Respuesta inválida del modelo para el núcleo %s (%s)" % (nuc["numero"], last))

    # ------------------------------------------------- banco de preguntas
    @api.model
    def generate_bank(self, course, cert, syl, research, instructions=None):
        """Amplía el banco del simulador con preguntas por dominio (proporcional al peso)."""
        if not cert or not cert.domain_ids:
            return 0
        target = max(int((cert.num_questions or 20) * 1.5), 24)
        have = len(course.question_ids)
        missing = max(target - have, 0)
        if not missing:
            return 0
        dist = ", ".join("%s: %d" % (d.name, max(1, round(missing * (d.weight or 0) / 100.0)))
                         for d in cert.domain_ids)
        prompt = ("Genera %d preguntas tipo examen %s (%s) para el curso «%s», distribuidas así por dominio: %s. "
                  "Preguntas de escenario, 4 opciones, 1 correcta, retroalimentación por opción y explicación. "
                  "Basadas en estos núcleos: %s.\nResponde SOLO un JSON: [{\"domain\": str (nombre exacto del "
                  "dominio), \"question\": str, \"explanation\": str, \"options\": [{\"text\": str, "
                  "\"correct\": bool, \"feedback\": str}]}]") % (
            missing, cert.name, cert.exam_code or "", course.name, dist,
            "; ".join("%s (%s)" % (n["titulo"], ", ".join(n.get("temas") or [])) for n in syl["nucleos"])[:4000])
        data = self._json(self._call(self.NUCLEO_SYSTEM, [{"role": "user", "content": prompt}], 12000))
        qs = data if isinstance(data, list) else data.get("questions", [])
        before = len(course.question_ids)
        self._create_questions(course, qs)
        return len(course.question_ids) - before

    @api.model
    def import_question_items(self, course, items, default_domain="General"):
        """Importa preguntas GIFT: usa el dominio de $CATEGORY y vincula el núcleo indicado.
        Omite preguntas repetidas (mismo enunciado) para poder reimportar sin duplicar."""
        existing = set(course.question_ids.mapped("name"))
        sections = {}
        for sec in course.section_ids:
            m = re.match(r"(?i)\s*n[úu]cleo\s+(\d+)", sec.name or "")
            if m:
                sections[int(m.group(1))] = sec
        before = len(course.question_ids)
        for q in items:
            if q.get("question") in existing:
                continue
            q.setdefault("domain", default_domain or "General")
            self._create_questions(course, [q], source="gift", section=sections.get(q.get("nucleo")))
            existing.add(q.get("question"))
        return len(course.question_ids) - before

    def _create_questions(self, course, questions, source="ai", section=None):
        Q = self.env["campus.question"].sudo()
        for q in questions or []:
            if not isinstance(q, dict):
                continue
            opts = [o for o in q.get("options") or [] if isinstance(o, dict)]
            if not q.get("question") or len(opts) < 2 or sum(1 for o in opts if o.get("correct")) != 1:
                continue
            Q.create({"course_id": course.id, "domain": q.get("domain") or "General",
                      "section_id": section.id if section else False,
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
                "Eres el Tutor IA de InnovaTech Lab (Politécnico Internacional). Acompañas a %s en el curso. "
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
