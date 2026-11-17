# -*- coding: utf-8 -*-
"""Agente de diseño instruccional: syllabus -> curso completo, por etapas y en segundo plano.

Etapas
1. Lectura del syllabus PI-GA-FT-141 (núcleos, objetivos, criterios, bibliografía).
2. Certificación objetivo (la elegida, la detectada en el syllabus o la que encuentre la investigación).
3. Investigación profunda en la web (Claude + búsqueda web): versión vigente de la certificación,
   novedades por núcleo y recursos abiertos, con sus fuentes.
4. Estructura y cronograma (Inicio, núcleos del syllabus, Cierre).
5. Contenido de cada núcleo: lectura, presentación, infografía, video (guion), actividad,
   laboratorio, evaluación con rúbrica según el instrumento del syllabus, sesión virtual,
   sesión presencial asistida por IA y cuestionario.
6. Banco de preguntas del simulador por dominio de la certificación.
7. Inicio y cierre (guía del estudiante, ruta de certificación, diagnóstico, autoevaluación, simulacro).
8. Fuentes y bitácora.

Sin API key cada etapa tiene un respaldo basado únicamente en el syllabus.
"""
import base64
import json
import logging
import re
import threading
import zipfile
from xml.etree import ElementTree
import time as _time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.modules.registry import Registry
from odoo.tools import html_escape

from ..tools import deck as deck_tools
from ..tools import kit as kit_tools
from ..tools import material as mat_tools
from ..tools import syllabus as syl_tools

_logger = logging.getLogger(__name__)

STAGES = [
    ("parse", "Leer el syllabus"),
    ("cert", "Identificar la certificación"),
    ("research", "Investigación profunda en la web"),
    ("structure", "Estructura y cronograma"),
    ("content", "Contenido de los núcleos"),
    ("bank", "Banco de preguntas del simulador"),
    ("frame", "Inicio y cierre del curso"),
    ("sources", "Fuentes, bitácora e inscripciones"),
]

NUCLEO_SCHEMA = """{
 "lectura": {"titulo": str, "resumen": str (máx. 240 caracteres),
   "presentacion": str (2 párrafos que enganchan: por qué importa el tema, cómo se conecta con el proyecto),
   "logros": [str] (3-4, inician con verbo en infinitivo),
   "secciones_html": str (secciones numeradas <h3>1. …</h3> con <h4>1.1 …</h4>, párrafos, al menos una tabla
      <table class='table'> con <tr><th>, ejemplos de código en <pre><code>…</code></pre> con <p class='caption'>Código N. …</p>,
      y 1-2 recuadros <div class='cp-callout'><b>Título</b><p>…</p></div>),
   "buenas_practicas": [str] (5-6),
   "casos": [{"titulo": str, "texto": str}] (3 casos para reflexionar, situaciones reales con una pregunta),
   "glosario": [{"termino": str, "significado": str}] (8-12),
   "referencias": [str] (formato APA 7, solo fuentes reales de la investigación o del syllabus)},
 "bibliografia": {"principal": [{"titulo": str, "autor": str, "url": str, "tema": str, "paginas": str, "referencia": str}],
                  "complementaria": [{"titulo": str, "autor": str, "url": str, "referencia": str}]},
 "infografia": {"titulo": str, "pregunta_orientadora": str, "texto_orientador": str (máx. 300 caracteres),
   "dato_clave": str, "terminos": [{"termino": str (máx. 25 caracteres), "texto": str (máx. 200 caracteres),
   "icono": str (uno de ICONOS), "etiqueta": str (2-4 palabras para la imagen)}] (10-14)},
 "caso": {"titulo": str, "tiempo_horas": int, "peso": str, "contexto": str (historia de una organización colombiana
   ficticia, 2-3 párrafos), "introduccion_indicaciones": str, "indicaciones": [str] (5-8 pasos verificables),
   "entregables": [str], "cierre": str, "solucion": [{"escenario": str, "accion": str, "resultado": str}],
   "revision_docente": [str], "rubrica": [{"criterio": str, "bueno": str, "regular": str, "insuficiente": str,
   "puntaje": float}] (4 criterios que suman 5,0)} | null,
 "laboratorio": {"titulo": str, "resumen": str, "html": str, "recurso_url": str} | null,
 "sesion_virtual": {"resumen": str, "agenda_html": str},
 "sesion_presencial": {"resumen": str, "guion_ia_html": str},
 "preguntas": [{"domain": str, "question": str, "explanation": str,
                "options": [{"text": str, "correct": bool, "feedback": str}]}]
}"""

MEDIA_SCHEMA = """{
 "escenas": [{"layout": "portada|puntos|codigo|tabla|proceso|comparacion|cita|cierre",
   "title": str (máx. 60 caracteres), "subtitle": str,
   "points": [str] (2-5 frases cortas de máx. 70 caracteres; lo que se ve en pantalla, no lo que se dice),
   "code": str (solo si layout=codigo, máx. 14 líneas), "code_lang": str,
   "table": {"headers": [str], "rows": [[str]]} (solo si layout=tabla),
   "icon": str (uno de ICONOS), "icon_label": str (2-4 palabras),
   "narration": str (lo que dice el docente: 110-170 palabras, ver reglas de voz)}] (12-16 escenas),
 "busqueda_youtube": str,
 "actividad": {"titulo": str, "objetivo": str, "instruccion": str,
   "preguntas": [{"escena": int (número de la escena después de la cual aparece), "enunciado": str (caso aplicado),
     "opciones": [{"texto": str, "correcta": bool, "retro": str (por qué es correcta o incorrecta)}] (4 opciones, 1 correcta)}]
   (10-15 preguntas)}
}"""

RESEARCH_SCHEMA = """{
 "certificacion": {"proveedor": str, "nombre": str, "codigo": str, "version": str, "estado": str,
   "url": str, "preguntas": int, "duracion_min": int, "puntaje_aprobacion": str, "precio": str,
   "idiomas": str, "dominios": [{"nombre": str, "peso": float}], "notas": str} | null,
 "nucleos": [{"numero": int, "novedades": [str], "conceptos_clave": [str],
              "recursos": [{"titulo": str, "url": str, "tipo": str}]}],
 "bibliografia": [str],
 "advertencias": [str]
}"""


def _thread_run(dbname, job_id, uid):
    _time.sleep(0.5)  # deja terminar la transacción que creó el trabajo
    try:
        registry = Registry(dbname)
        with registry.cursor() as cr:
            env = api.Environment(cr, uid, {"lang": "es_CO", "tz": "America/Bogota"})
            env["campus.agent.job"].browse(job_id)._run()
    except Exception:  # noqa: BLE001
        _logger.exception("Fallo del agente %s", job_id)


class CampusAgentJob(models.Model):
    _name = "campus.agent.job"
    _description = "Ejecución del agente de diseño instruccional"
    _order = "id desc"

    name = fields.Char("Curso solicitado", required=True)
    state = fields.Selection([("queued", "En cola"), ("running", "Trabajando"), ("done", "Terminado"),
                              ("error", "Con error")], default="queued", required=True)
    stage = fields.Char("Etapa actual")
    progress = fields.Integer("Avance (%)")
    log = fields.Text("Bitácora", default="")
    error = fields.Text("Error")
    user_id = fields.Many2one("res.users", "Solicitado por", default=lambda s: s.env.user)
    course_id = fields.Many2one("campus.course", "Curso generado", ondelete="set null")
    certification_id = fields.Many2one("campus.certification", "Certificación")
    params = fields.Json("Parámetros")
    syllabus_file = fields.Binary("Syllabus", attachment=True)
    syllabus_filename = fields.Char("Archivo")
    syllabus_json = fields.Json("Syllabus interpretado")
    research_json = fields.Json("Investigación")
    use_ai = fields.Boolean("Con IA")
    deep_research = fields.Boolean("Investigación web", default=True)
    heartbeat = fields.Datetime("Última actividad")
    provider = fields.Char("Proveedor de IA")
    date_done = fields.Datetime("Terminado el")

    # --------------------------------------------------------- utilidades
    def _say(self, msg, progress=None, stage=None):
        self.ensure_one()
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
        vals = {"log": ((self.log or "") + line + "\n")[-20000:], "heartbeat": fields.Datetime.now()}
        if progress is not None:
            vals["progress"] = max(0, min(100, int(progress)))
        if stage:
            vals["stage"] = stage
        self.sudo().write(vals)
        _logger.info("Agente %s: %s", self.id, msg)
        if not self.env.context.get("agent_sync"):
            self.env.cr.commit()

    def is_stale(self):
        self.ensure_one()
        return (self.state in ("queued", "running") and self.heartbeat
                and fields.Datetime.now() - self.heartbeat > timedelta(minutes=12))

    def action_start(self, background=True):
        for job in self:
            job.write({"state": "queued", "progress": 0, "error": False, "heartbeat": fields.Datetime.now()})
            if background:
                self.env.cr.postcommit.add(lambda j=job: threading.Thread(
                    target=_thread_run, args=(self.env.cr.dbname, j.id, self.env.uid),
                    name="campus-agent-%s" % j.id, daemon=True).start())
            else:
                job.with_context(agent_sync=True)._run()
        return True

    def action_retry(self):
        for job in self:
            if job.course_id and job.state != "done":
                job.course_id.sudo().unlink()
            job.write({"log": (job.log or "") + "\n--- Reintento ---\n"})
        return self.action_start()

    # ------------------------------------------------------------ pipeline
    def _run(self):
        self.ensure_one()
        agent = self.env["campus.ai.agent"].sudo()
        use_ai = agent.is_enabled() and (self.params or {}).get("use_ai", True)
        self.write({"state": "running", "use_ai": use_ai,
                    "provider": agent.provider_label() if use_ai else "Sin IA (solo syllabus)"})
        try:
            p = self.params or {}
            # 1. Syllabus
            target = self.regenerate_course_id
            if target and not self.use_ai:
                raise UserError(_("Para regenerar un curso con los agentes configure un proveedor de IA "
                                  "(Gemini o Groq gratis, Claude o ChatGPT) en «Proveedor de IA»."))
            self._say("Leyendo el syllabus «%s»…" % (self.syllabus_filename or (
                "del curso «%s»" % target.name if target else "syllabus")), 3, "parse")
            raw = base64.b64decode(self.syllabus_file or b"")
            if target and not self.syllabus_file:
                syl = target._syllabus_from_course()
                self._say("Regenerando «%s» con los agentes actuales: se conserva su estructura de núcleos y el "
                          "contenido actual se usa como material del docente." % target.name, 4)
            elif self.syllabus_filename and self.syllabus_filename.lower().endswith(".pdf"):
                text = agent.extract_text(self.syllabus_file, self.syllabus_filename)
                syl = syl_tools.parse_text(text)
            else:
                try:
                    syl = syl_tools.parse(raw, self.syllabus_filename)
                except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
                    raise UserError(_("El archivo «%s» está dañado o no es un documento Word válido. "
                                      "Ábralo en Word, guárdelo de nuevo como .docx o súbalo en PDF.") % self.syllabus_filename)
            is_docx = (self.syllabus_filename or "").lower().endswith(".docx")
            weak = not is_docx or not syl.get("nucleos") or not any(n.get("temas") for n in syl["nucleos"])
            if target and not self.syllabus_file and syl.get("nucleos"):
                weak = False
            if self.use_ai and weak:
                self._say("El formato no es DOCX o la tabla de alineación no es legible: Claude interpreta la estructura…", 5)
                try:
                    st = agent.structure_syllabus(syl.get("texto") or "")
                    nucs = [n for n in st.get("nucleos") or [] if isinstance(n, dict) and n.get("titulo")]
                    if nucs:
                        for i, n in enumerate(nucs, 1):
                            n.setdefault("numero", i)
                            for k in ("temas", "estrategias", "criterios"):
                                n[k] = [str(x) for x in n.get(k) or []]
                            n["objetivo"] = n.get("objetivo") or ""
                        syl["nucleos"] = nucs
                    for k in ("asignatura", "resultado_aprendizaje", "competencias", "producto"):
                        if st.get(k) and not syl.get(k):
                            syl[k] = st[k]
                    if st.get("objetivos") and not syl.get("objetivos"):
                        syl["objetivos"] = st["objetivos"]
                    if st.get("evaluacion") and not syl.get("evaluacion"):
                        syl["evaluacion"] = [dict(e, criterios=[], para_que="") for e in st["evaluacion"] if isinstance(e, dict)]
                except Exception as e:  # noqa: BLE001
                    self._say("⚠️ No se pudo interpretar con IA (%s); se usa la lectura automática." % str(e)[:150])
            if not syl.get("nucleos"):
                syl["nucleos"] = [{"numero": i, "titulo": "Unidad %s" % i, "temas": [], "objetivo": "",
                                   "estrategias": [], "criterios": []} for i in range(1, 5)]
                self._say("⚠️ No se encontraron núcleos en el syllabus: se crean 4 unidades base.")
            self.syllabus_json = syl
            self._say("Syllabus: %s · %d núcleos · %d objetivos · %d criterios de evaluación · %d referencias." % (
                syl.get("asignatura") or "(sin nombre)", len(syl["nucleos"]), len(syl.get("objetivos") or []),
                len(syl.get("evaluacion") or []),
                len(syl.get("bibliografia") or []) + len(syl.get("cibergrafia") or [])), 8)

            # 1b. Material del docente (opcional)
            if self.material_ids:
                self._say("Leyendo el material del curso (%d archivo(s))…" % len(self.material_ids), 9)
                mats = self.material_ids._expand()
                with_text = mats.filtered(lambda m: (m.text or "").strip() and not (m.text or "").startswith("[No se pudo"))
                self._say("Material: %d archivo(s), %d con texto utilizable. %s" % (
                    len(mats), len(with_text), mat_tools.summarize(
                        [{"name": m.path or m.name, "kind": m.kind, "nucleo": m.nucleo} for m in mats], 1500)), 10)
                nums = {n["numero"] for n in syl["nucleos"]}
                lost = mats.filtered(lambda m: m.nucleo and m.nucleo not in nums)
                if lost:
                    lost.write({"nucleo": 0})
                    self._say("ℹ️ %d archivo(s) mencionan un núcleo que no existe en el syllabus: se usan como material general." % len(lost))

            # 2. Certificación
            cert = self.certification_id
            if not cert and p.get("cert_mode") == "auto":
                cert = self._detect_certification(syl, p.get("instructions"))
                if cert:
                    self._say("Certificación detectada en el syllabus: %s (%s)." % (cert.name, cert.exam_code), 10, "cert")
            # 3. Investigación
            research = {}
            if self.use_ai and self.deep_research:
                self._say("Proveedor de IA: %s." % self.provider, 11)
                self._say(("Investigando en la web: versión vigente de la certificación, novedades y recursos por núcleo…"
                           if agent.has_web_search() else
                           "Investigando (este proveedor no tiene búsqueda web: se usa el conocimiento del modelo y "
                           "los datos quedan marcados para verificar)…"), 12, "research")
                try:
                    research = agent.research_course(syl, cert, p.get("instructions"))
                    self._say("Investigación: %d fuentes consultadas." % len(research.get("_sources") or []), 25)
                    for w in research.get("advertencias") or []:
                        self._say("ℹ️ %s" % w)
                except Exception as e:  # noqa: BLE001
                    self._say("⚠️ La investigación falló (%s). Se continúa con el syllabus." % str(e)[:200], 25)
                    research = {}
            else:
                self._say("Investigación web omitida (%s). Se usan las referencias del syllabus." % (
                    "no hay proveedor de IA configurado" if not self.use_ai else "desactivada"), 25, "research")
            if not cert and p.get("cert_mode") == "auto" and research.get("certificacion"):
                cert = self._certification_from_research(research["certificacion"])
                if cert:
                    self._say("Certificación objetivo según la investigación: %s (%s)." % (cert.name, cert.exam_code))
            self.research_json = research
            self.certification_id = cert

            # 4. Estructura
            self._say("Creando estructura y cronograma…", 28, "structure")
            course, sections = self._create_structure(syl, cert, p)
            self.course_id = course
            self._say("Curso «%s» con %d secciones." % (course.name, len(sections)), 30)

            # 5. Núcleos
            self._say("Generando el contenido de %d núcleos%s…" % (
                len(syl["nucleos"]), (" con " + (self.provider or "IA")) if self.use_ai else " a partir del syllabus"), 31, "content")
            contents = self._nucleo_contents(syl, cert, research, p)
            n = len(syl["nucleos"])
            for i, (nuc, sec) in enumerate(zip(syl["nucleos"], sections[1:-1])):
                data = contents[i]
                self._create_nucleo_lessons(sec, nuc, data, syl, cert, p)
                self._say("Núcleo %s listo: %d lecciones, %d preguntas." % (
                    nuc["numero"], len(sec.lesson_ids),
                    self.env["campus.question"].sudo().search_count([("section_id", "=", sec.id)])),
                    31 + 50 * (i + 1) / n)

            # 6. Banco del simulador
            self._say("Preparando el banco de preguntas del simulador…", 82, "bank")
            if self.use_ai:
                try:
                    added = agent.generate_bank(course, cert, syl, research, p.get("instructions"))
                    self._say("Banco del simulador: %d preguntas nuevas por dominio." % added)
                except Exception as e:  # noqa: BLE001
                    self._say("⚠️ No se pudo ampliar el banco (%s)." % str(e)[:200])
            if cert and len(course.question_ids) < (cert.num_questions or 20):
                reused = self._reuse_bank(course, cert)
                if reused:
                    self._say("Se reutilizaron %d preguntas de otros cursos de %s." % (reused, cert.exam_code or cert.name))
            if not course.question_ids:
                self._say("ℹ️ El banco del simulador está vacío: impórtelo en formato GIFT o configure la API key para generarlo.")
            self._say("Banco total: %d preguntas." % len(course.question_ids), 88)

            # 7. Inicio y cierre
            self._say("Creando inicio (guía, ruta de certificación, diagnóstico) y cierre…", 90, "frame")
            self._create_frame(course, sections[0], sections[-1], syl, cert, research, p)

            if self.roster_students or self.roster_teachers:
                self._say("Cargando la hoja de estudiantes y docentes… " + self._import_rosters(course), 91)
            if self.material_ids.filtered("file"):
                n_pub = self._publish_materials(course)
                self._say("Material del docente publicado en el curso (%d lección(es) de apoyo)." % n_pub, 92)

            # 8. Fuentes y cierre
            course.sources_html = self._sources_html(syl, research, cert)
            if p.get("student_ids"):
                course.enroll_users(self.env["res.users"].browse(p["student_ids"]))
            course.ai_log = (self.log or "")[-8000:]
            if target:
                self._say("Reemplazando el contenido de «%s» por el nuevo (inscripciones, docentes, banco de preguntas "
                          "y microcredenciales se conservan)…" % target.name, 97)
                course = self._swap_into(target, course)
            self.write({"state": "done", "date_done": fields.Datetime.now()})
            self._say("✅ Curso listo: %d lecciones y %d preguntas. Revísalo y publícalo." % (
                len(course.lesson_ids), len(course.question_ids)), 100, "sources")
        except Exception as e:  # noqa: BLE001
            _logger.exception("Agente %s", self.id)
            if not self.env.context.get("agent_sync"):
                self.env.cr.rollback()
            msg = e.args[0] if isinstance(e, UserError) else "%s: %s" % (type(e).__name__, e)
            if self.regenerate_course_id and self.course_id and self.course_id != self.regenerate_course_id:
                try:
                    self.course_id.sudo().unlink()  # el curso original queda intacto
                except Exception:  # noqa: BLE001
                    _logger.exception("No se pudo borrar el curso temporal")
            self.write({"state": "error", "error": str(msg)[:2000]})
            self._say("❌ Error: %s" % str(msg)[:500])
        return True

    # ---------------------------------------------------- certificación
    def _detect_certification(self, syl, instructions=None):
        text = " ".join([syl.get("texto") or "", syl.get("asignatura") or "", instructions or ""]).lower()
        best, score = None, 0
        for c in self.env["campus.certification"].sudo().search([]):
            s = 0
            code = (c.exam_code or "").lower().strip()
            if code and len(code) >= 4 and code in text:
                s += 3
            if c.name and c.name.lower() in text:
                s += 2
            if s > score:
                best, score = c, s
        return best if score >= 2 else None

    def _certification_from_research(self, info):
        if not info or not info.get("nombre"):
            return None
        Cert = self.env["campus.certification"].sudo()
        code = (info.get("codigo") or "").strip()
        if code:
            found = Cert.search([("exam_code", "=ilike", code)], limit=1)
            if found:
                return found
        doms = [d for d in info.get("dominios") or [] if d.get("nombre")]
        pass_txt = str(info.get("puntaje_aprobacion") or "")
        m = re.search(r"(\d+)\s*(?:/|de|sobre|on a scale of [\d]+ to)\s*(\d+)", pass_txt)
        passing = 70.0
        if m and float(m.group(2)) > 0:
            passing = round(100.0 * float(m.group(1)) / float(m.group(2)), 0)
        return Cert.create({
            "name": info["nombre"][:120], "provider": (info.get("proveedor") or "Por confirmar")[:80],
            "exam_code": code[:40], "url": info.get("url"),
            "passing_score": passing, "num_questions": 30, "duration_min": 45,
            "price_note": (info.get("precio") or "")[:250],
            "verify_note": ("Creada por el agente con investigación web (%s). Oficial: %s preguntas, %s min, "
                            "aprobación %s. Verificar antes de cada cohorte.") % (
                fields.Date.today(), info.get("preguntas") or "?", info.get("duracion_min") or "?", pass_txt or "?"),
            "description": "<p>%s</p>" % html_escape(info.get("notas") or info.get("estado") or ""),
            "domain_ids": [(0, 0, {"sequence": i, "name": d["nombre"][:120], "weight": float(d.get("peso") or 0)})
                           for i, d in enumerate(doms)],
        })

    # ------------------------------------------------------ estructura
    def _create_structure(self, syl, cert, p):
        d0 = fields.Date.to_date(p.get("date_start")) or fields.Date.context_today(self)
        d1 = fields.Date.to_date(p.get("date_end")) or (d0 + timedelta(weeks=16))
        nucleos = syl["nucleos"]
        hours = int((re.search(r"\d+", syl.get("horas") or "") or [144])[0]) if syl.get("horas") else 144
        objetivos = syl.get("objetivos") or []
        outcomes = "<p><b>Resultado de aprendizaje:</b> %s</p>" % html_escape(syl.get("resultado_aprendizaje") or "-")
        if syl.get("competencias"):
            outcomes += "<p><b>Competencia:</b> %s</p>" % html_escape(syl["competencias"])
        if objetivos:
            outcomes += "<ul>%s</ul>" % "".join("<li>%s</li>" % html_escape(o) for o in objetivos)
        if syl.get("producto"):
            outcomes += "<p><b>Producto:</b> %s</p>" % html_escape(syl["producto"])
        desc = "".join("<p>%s</p>" % html_escape(x) for x in (syl.get("descripcion") or "").split("\n\n") if x.strip())
        course = self.env["campus.course"].sudo().create({
            "name": ("[Regenerando] " if self.regenerate_course_id else "") + (p.get("name") or syl.get("asignatura") or "Curso"),
            "subtitle": (("Ruta hacia %s (%s)" % (cert.name, cert.exam_code)) if cert else syl.get("programa") or "")[:200],
            "description": desc or "<p>%s</p>" % html_escape(syl.get("contenidos") or ""),
            "outcomes": outcomes,
            "skills": ", ".join(t.strip(" .") for t in re.split(r"\.\s+", syl.get("contenidos") or "") if 2 < len(t) < 60)[:250],
            "hours": hours, "modality": p.get("modality") or "virtual",
            "date_start": d0, "date_end": d1, "certification_id": cert.id if cert else False,
            "teacher_ids": [(6, 0, p.get("teacher_ids") or [])],
            "syllabus_file": self.syllabus_file, "syllabus_filename": self.syllabus_filename,
            "syllabus_text": (syl.get("texto") or "")[:100000],
            "ai_generated": True, "state": "draft", "agent_job_id": self.id,
            "tutor_prompt": p.get("instructions") or False,
        })
        Section = self.env["campus.section"].sudo()
        total = max((d1 - d0).days, 7)
        intro_days = max(min(7, total // 10), 1)
        close_days = max(min(10, total // 8), 1)
        span = max(total - intro_days - close_days, len(nucleos))
        step = max(span // max(len(nucleos), 1), 1)
        sections = [Section.create({"course_id": course.id, "sequence": 0, "name": "Inicio",
                                    "objective": "Bienvenida, guía del estudiante, ruta de certificación y diagnóstico inicial.",
                                    "date_start": d0, "date_end": d0 + timedelta(days=intro_days - 1)})]
        cur = d0 + timedelta(days=intro_days)
        for i, nuc in enumerate(nucleos):
            end = min(cur + timedelta(days=step - 1), d1)
            sections.append(Section.create({
                "course_id": course.id, "sequence": i + 1,
                "name": "Núcleo %s – %s" % (nuc["numero"], nuc["titulo"])[:180] if not re.match(r"(?i)n[úu]cleo", nuc["titulo"]) else nuc["titulo"],
                "objective": nuc.get("objetivo") or "", "date_start": cur, "date_end": end}))
            cur = end + timedelta(days=1)
        sections.append(Section.create({"course_id": course.id, "sequence": len(nucleos) + 1, "name": "Cierre",
                                        "objective": "Autoevaluación, diagnóstico final, simulacro y plan para presentar el examen.",
                                        "date_start": min(cur, d1), "date_end": d1}))
        return course, sections

    # ------------------------------------------------------ contenido
    def _nucleo_contents(self, syl, cert, research, p):
        agent = self.env["campus.ai.agent"].sudo()
        nucleos = syl["nucleos"]
        if not self.use_ai:
            return [self._offline_nucleo(n, syl, cert) for n in nucleos]
        summary = syl_tools.summary(syl)
        conf = agent.bulk_conf() if self.economy else agent._llm_conf()  # se lee antes: los hilos no tocan la BD
        if self.economy:
            self._say("Modo económico: modelo %s, video de 9-11 escenas y actividad de 8 casos." % conf["model"])
        cinfo = None
        if cert:
            cinfo = {"name": cert.name, "provider": cert.provider, "code": cert.exam_code,
                     "domains": [(d.name, d.weight) for d in cert.domain_ids]}
        instructions = p.get("instructions")
        cases = {n["numero"]: self._instrumento(syl, n) in ("Proyecto", "Laboratorio") for n in nucleos}
        mctx = {n["numero"]: self._material_context(n["numero"]) for n in nucleos}
        economy = bool(self.economy)
        course_name = p.get("name") or syl.get("asignatura") or ""

        def work(task):
            kind, nuc = task
            try:
                if kind == "content":
                    return agent.nucleo_content_payload(summary, nuc, cinfo, research, instructions, conf=conf,
                                                        with_case=cases.get(nuc["numero"], False),
                                                        material=mctx.get(nuc["numero"]) or None)
                return agent.nucleo_media_payload(summary, nuc, cinfo, research, instructions, conf=conf,
                                                  course_name=course_name, material=mctx.get(nuc["numero"]) or None,
                                                  economy=economy)
            except Exception as e:  # noqa: BLE001
                return {"_error": str(e)[:300]}

        from ..tools import llm
        workers = llm.PROVIDERS.get(conf["provider"], {}).get("parallel", 1)
        tasks = [(k, n) for n in nucleos for k in ("content", "media")]
        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(tasks)))) as ex:
            results = list(ex.map(work, tasks))
        agent._remember_model(conf)
        out = []
        for i, nuc in enumerate(nucleos):
            res, media = results[2 * i], results[2 * i + 1]
            base = None
            if res.get("_error"):
                self._say("⚠️ Núcleo %s: la IA falló en la lectura (%s); se usa contenido base del syllabus." % (
                    nuc["numero"], res["_error"][:150]))
                base = self._offline_nucleo(nuc, syl, cert)
                res = base
            if media.get("_error"):
                self._say("⚠️ Núcleo %s: la IA falló en el video y la actividad (%s); se arman a partir de la lectura." % (
                    nuc["numero"], media["_error"][:150]))
                media = (base or self._offline_nucleo(nuc, syl, cert))["_media"]
            res = dict(res)
            res["_media"] = media
            out.append(res)
        return out

    def _offline_nucleo(self, nuc, syl, cert):
        """Contenido base sin IA, con la misma estructura de los formatos institucionales."""
        temas = [t.rstrip(". ") for t in (nuc.get("temas") or [nuc["titulo"]]) if t.strip()]
        crit = nuc.get("criterios") or []
        refs = (syl.get("bibliografia") or [])[:4] + (syl.get("cibergrafia") or [])[:4]
        asig = syl.get("asignatura") or ""
        e = html_escape
        secciones = []
        for i, t in enumerate(temas, 1):
            secciones.append(
                "<h3>%d. %s</h3><p>En este apartado estudiarás <b>%s</b> dentro de la asignatura %s. Revisa la "
                "bibliografía sugerida y construye tu propia explicación respondiendo tres preguntas: ¿qué problema "
                "resuelve este concepto?, ¿cómo se aplica en una organización colombiana? y ¿qué errores comunes "
                "debes evitar?</p>" % (i, e(t), e(t.lower()), e(asig)))
        if crit:
            secciones.append("<h3>%d. ¿Cómo se evalúa?</h3><ul>%s</ul>" % (
                len(temas) + 1, "".join("<li>%s</li>" % e(c) for c in crit)))
        mtxt = self._material_context(nuc["numero"], 20000, 3000) if self.material_ids else ""
        if mtxt:
            secciones.append("<h3>%d. Material del docente</h3>%s" % (len(secciones) + 1, "".join(
                "<p>%s</p>" % e(par.strip()) for par in re.split(r"\n\s*\n", mtxt) if par.strip())[:60000]))
        kit_data = {
            "lectura": {
                "titulo": nuc["titulo"], "resumen": nuc.get("objetivo") or "",
                "presentacion": "Este núcleo te acerca a %s. A lo largo de la lectura encontrarás los conceptos clave, "
                                "preguntas para conectar cada tema con tu práctica y la forma en que se evalúa." % nuc["titulo"],
                "logros": ["Comprender %s." % (t[0].lower() + t[1:]) for t in temas[:4] if t],
                "secciones_html": "".join(secciones),
                "buenas_practicas": ["Lee la lectura completa antes de la sesión sincrónica.",
                                     "Relaciona cada concepto con un caso real.",
                                     "Consulta al tutor IA cuando una idea no quede clara."],
                "casos": [], "glosario": [{"termino": t[:60], "significado": "Concepto central del núcleo."} for t in temas[:8]],
                "referencias": refs,
            },
            "bibliografia": {"principal": [{"titulo": r, "autor": "", "url": "", "tema": nuc["titulo"], "paginas": "",
                                            "referencia": r} for r in (syl.get("bibliografia") or [])[:2]],
                             "complementaria": [{"titulo": r, "autor": "", "url": "", "referencia": r}
                                                for r in (syl.get("cibergrafia") or [])[:6]]},
        }
        escenas = [{"layout": "portada", "title": nuc["titulo"], "subtitle": "Núcleo %s" % nuc["numero"],
                    "points": [nuc.get("objetivo") or ""]}]
        for t in temas:
            escenas.append({"layout": "puntos", "title": t, "points": [
                "Qué es y qué problema resuelve", "Cómo se aplica en un caso real",
                "Errores comunes que debes evitar"]})
        if crit:
            escenas.append({"layout": "puntos", "title": "Así se evalúa", "points": crit[:5], "icon": "objetivo"})
        escenas.append({"layout": "cierre", "title": "Para continuar",
                        "points": ["Lee la lectura del núcleo", "Resuelve la actividad interactiva", "Prepara la evaluación"]})
        instrumento = self._instrumento(syl, nuc)
        eval_html = "<h4>Instrucciones</h4><p>%s</p><h4>Criterios de evaluación</h4><ul>%s</ul>%s" % (
            e("Desarrolla la actividad evaluativa del núcleo (%s) aplicando los temas: %s." % (
                instrumento.lower(), "; ".join(temas))),
            "".join("<li>%s</li>" % e(c) for c in crit), _rubric(crit))
        agenda = ("<h4>Agenda (90 min)</h4><ol><li>Saludo y resolución de dudas (10 min)</li>"
                  "<li>Explicación guiada: %s (35 min)</li><li>Ejercicio práctico en grupos (30 min)</li>"
                  "<li>Cierre y preguntas tipo examen (15 min)</li></ol>") % e(", ".join(temas[:4]))
        guion = ("<h4>Guion del agente IA (sesión presencial)</h4><ol><li><b>Diagnóstico (10 min):</b> 3 preguntas "
                 "rápidas sobre %s.</li><li><b>Preguntas detonantes:</b> ¿qué pasaría si…? aplicado a un caso local.</li>"
                 "<li><b>Reto práctico (60 min):</b> por equipos, resolver un problema del núcleo; el agente da pistas "
                 "graduales sin entregar la solución.</li><li><b>Cierre (15 min):</b> el agente resume errores frecuentes y "
                 "propone 3 preguntas tipo examen.</li></ol>") % e(nuc["titulo"])
        kit_data.update({
            "infografia": {"titulo": nuc["titulo"], "pregunta_orientadora": nuc.get("objetivo") or "",
                           "texto_orientador": (nuc.get("objetivo") or "")[:300], "dato_clave": "",
                           "terminos": [{"termino": t[:25], "texto": "", "icono": "", "etiqueta": t[:30]} for t in temas[:12]]},
            "caso": None, "laboratorio": None,
            "evaluacion": {"titulo": "%s del Núcleo %s" % (instrumento, nuc["numero"]),
                           "resumen": "Actividad evaluativa definida en el syllabus.", "html": eval_html},
            "sesion_virtual": {"resumen": "Encuentro sincrónico con el docente.", "agenda_html": agenda},
            "sesion_presencial": {"resumen": "Sesión presencial asistida por el agente IA.", "guion_ia_html": guion},
            "preguntas": [],
            "_media": {"escenas": escenas, "busqueda_youtube": "%s %s" % (nuc["titulo"], cert.exam_code if cert else ""),
                       "actividad": {"titulo": "Actividad formativa: %s" % nuc["titulo"],
                                     "objetivo": nuc.get("objetivo") or "",
                                     "instruccion": "Elabora un mapa conceptual de los temas del núcleo (%s) y pide "
                                                    "retroalimentación al tutor IA." % "; ".join(temas),
                                     "preguntas": []}},
        })
        return kit_data

    def _instrumento(self, syl, nuc):
        for ev in syl.get("evaluacion") or []:
            if str(nuc["numero"]) in (ev.get("cuando") or ""):
                ins = ev.get("instrumento") or ""
                if re.search(r"(?i)proyecto|r[úu]brica|caso", ins):
                    return "Proyecto"
                if re.search(r"(?i)laboratorio|informe", ins):
                    return "Laboratorio"
                return "Cuestionario"
        return "Cuestionario"

    def _create_nucleo_lessons(self, sec, nuc, data, syl, cert, p):
        Lesson = self.env["campus.lesson"].sudo()
        seq = [0]

        def add(ltype, name, summary, content=None, **kw):
            seq[0] += 1
            vals = {"section_id": sec.id, "sequence": seq[0], "name": (name or ltype)[:200], "lesson_type": ltype,
                    "summary": (summary or "")[:250], "content": content or "<p>%s</p>" % html_escape(summary or "")}
            vals.update(kw)
            return Lesson.create(vals)

        kit = kit_tools.clean_kit(data)
        media = data.get("_media") or {}
        escenas = deck_tools.normalize(media.get("escenas") or (data.get("presentacion") or {}).get("slides"))
        act = kit_tools.clean_activity(media.get("actividad") or {})
        ig = data.get("infografia") or {}
        kit.update({"infografia": ig, "actividad": act})
        sec.kit_json = kit
        lec = kit["lectura"]
        lec_html = kit_tools.lectura_html(lec) if (lec.get("secciones_html") or lec.get("presentacion")) else \
            ((data.get("lectura") or {}).get("html") or "")
        add("lectura", "Lectura: %s" % (lec.get("titulo") or nuc["titulo"]), lec.get("resumen"), lec_html, duration_min=60)
        add("presentacion", "Presentación del núcleo", "Recorrido visual por los conceptos clave, con narración opcional.",
            slides_json=escenas or False, duration_min=30)
        add("infografia", "Infografía: %s" % (ig.get("titulo") or nuc["titulo"]),
            ig.get("pregunta_orientadora") or ig.get("dato_clave") or "Síntesis gráfica del núcleo.",
            infographic_json=ig, duration_min=10)
        add("video", "Video explicativo: %s" % nuc["titulo"],
            "Explicación narrada por escenas (aprox. %d min)." % max(1, deck_tools.timeline(escenas)[1] // 60) if escenas
            else "Explicación narrada del núcleo.",
            kit_tools.guion_html(escenas) if escenas else False,
            video_query=(media.get("busqueda_youtube") or "")[:200], slides_json=escenas or False,
            duration_min=max(10, deck_tools.timeline(escenas)[1] // 60 + 5) if escenas else 15)
        add("actividad", act.get("titulo") or "Actividad formativa interactiva",
            "%d preguntas tipo caso con retroalimentación inmediata." % len(act["preguntas"]) if act["preguntas"]
            else "Práctica guiada sin calificación.", kit_tools.actividad_html(act), activity_json=act["preguntas"] or False,
            duration_min=30 if act["preguntas"] else 45)
        bib = kit["bibliografia"]
        if bib["principal"] or bib["complementaria"]:
            add("lectura", "Recursos bibliográficos", "Libro guía y material de apoyo complementario del núcleo.",
                _bib_html(bib), duration_min=15)
        lab = data.get("laboratorio")
        if lab and lab.get("html"):
            url = lab.get("recurso_url") or ""
            add("laboratorio", lab.get("titulo") or "Laboratorio", lab.get("resumen"), lab.get("html"),
                resource_url=url if url.startswith("http") else False, duration_min=120)
        ev = data.get("evaluacion") or {}
        instrumento = self._instrumento(syl, nuc)
        caso = kit.get("caso")
        if caso:
            add("caso", caso["titulo"] or "Caso integrador", "Caso integrador con rúbrica%s." % (
                " (%s de la nota)" % caso["peso"] if caso.get("peso") else ""), kit_tools.caso_html(caso),
                duration_min=int(_num(caso.get("tiempo_horas") or 4) * 60))
        elif instrumento in ("Proyecto", "Laboratorio"):
            crit = nuc.get("criterios") or []
            add("caso", ev.get("titulo") or "%s del Núcleo %s" % (instrumento, nuc["numero"]),
                ev.get("resumen") or "Actividad evaluativa definida en el syllabus.",
                ev.get("html") or ("<h4>Criterios de evaluación</h4><ul>%s</ul>%s" % (
                    "".join("<li>%s</li>" % html_escape(c) for c in crit), _rubric(crit))), duration_min=240)
        d0 = sec.date_start or fields.Date.today()
        sv = data.get("sesion_virtual") or {}
        add("sesion_virtual", "Sesión sincrónica virtual", sv.get("resumen") or "Encuentro sincrónico con el docente.",
            ai_guide=sv.get("agenda_html"), duration_min=90,
            session_datetime=datetime.combine(d0 + timedelta(days=1), time(0, 0)),  # 7:00 p. m. Colombia
            meeting_url=(p.get("meeting_url") or False))
        sp = data.get("sesion_presencial") or {}
        sat = d0 + timedelta(days=(5 - d0.weekday()) % 7)
        add("sesion_presencial", "Sesión presencial asistida por IA",
            sp.get("resumen") or "Laboratorio presencial con el agente IA como co-tutor.",
            ai_guide=sp.get("guion_ia_html"), duration_min=120,
            session_datetime=datetime.combine(sat, time(13, 0)),  # 8:00 a. m. Colombia
            location=p.get("location") or "Sede Politécnico Internacional – laboratorio de sistemas")
        qs = data.get("preguntas") or []
        if qs:
            self.env["campus.ai.agent"].sudo()._create_questions(sec.course_id, qs, section=sec)
        if instrumento == "Cuestionario":
            add("quiz", ev.get("titulo") or "Cuestionario del Núcleo %s" % nuc["numero"],
                ev.get("resumen") or "Cuestionario evaluativo con calificación automática.", ev.get("html"), duration_min=45)
        else:
            add("quiz", "Cuestionario del Núcleo %s" % nuc["numero"],
                "Práctica con calificación automática y retroalimentación por opción.", duration_min=30)

    def _swap_into(self, old, new):
        """Pasa las secciones nuevas al curso original y elimina las anteriores. Conserva el registro del curso
        (inscripciones, docentes, microcredenciales, estado, fechas, ícono) y su banco de preguntas."""
        self.ensure_one()
        old, new = old.sudo(), new.sudo()

        def num(sec):
            return mat_tools.section_number(sec.name)
        old_qs = old.question_ids
        old_q_sec = {q.id: num(q.section_id) for q in old_qs if q.section_id}
        old_sections = old.section_ids
        new.section_ids.write({"course_id": old.id})
        names = set(old_qs.mapped("name"))
        new_qs = new.question_ids
        dup = new_qs.filtered(lambda q: q.name in names)
        dup.unlink()
        (new_qs - dup).exists().write({"course_id": old.id})
        new.material_ids.write({"course_id": old.id})
        old_sections.unlink()
        by_num = {num(s): s for s in old.section_ids if num(s)}
        for q in old_qs.exists():
            if old_q_sec.get(q.id) and by_num.get(old_q_sec[q.id]):
                q.section_id = by_num[old_q_sec[q.id]]
        old.write({k: new[k] for k in ("description", "outcomes", "sources_html", "ai_log") if new[k]})
        old.write({"ai_generated": True, "agent_job_id": self.id,
                   "skills": new.skills or old.skills, "hours": new.hours or old.hours})
        new.enrollment_ids.unlink()
        new.unlink()
        self.course_id = old
        return old

    def _reuse_bank(self, course, cert):
        Q = self.env["campus.question"].sudo()
        src = Q.search([("course_id.certification_id", "=", cert.id), ("course_id", "!=", course.id)], limit=200)
        names = set(course.question_ids.mapped("name"))
        n = 0
        for q in src:
            if q.name in names:
                continue
            q.copy({"course_id": course.id, "section_id": False, "source": q.source})
            names.add(q.name)
            n += 1
        return n

    # ------------------------------------------------------ inicio / cierre
    def _create_frame(self, course, intro, close, syl, cert, research, p):
        Lesson = self.env["campus.lesson"].sudo()
        e = html_escape
        guide = ["<h4>Bienvenida</h4><p>%s</p>" % e((syl.get("descripcion") or "").split("\n\n")[0] or course.name)]
        if syl.get("competencias"):
            guide.append("<h4>Competencia</h4><p>%s</p>" % e(syl["competencias"]))
        if syl.get("resultado_aprendizaje"):
            guide.append("<h4>Resultado de aprendizaje</h4><p>%s</p>" % e(syl["resultado_aprendizaje"]))
        if syl.get("producto"):
            guide.append("<h4>Producto</h4><p>%s</p>" % e(syl["producto"]))
        rows = "".join("<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            e("Núcleo %s – %s" % (n["numero"], n["titulo"])), e(n.get("objetivo") or ""),
            "<br/>".join(e(c) for c in n.get("criterios") or [])) for n in syl["nucleos"])
        guide.append("<h4>Ruta de aprendizaje</h4><table class='table'><tr><th>Núcleo</th><th>Objetivo</th>"
                     "<th>Criterios de evaluación</th></tr>%s</table>" % rows)
        if syl.get("evaluacion"):
            guide.append("<h4>Matriz de evaluación</h4><table class='table'><tr><th>Cuándo</th><th>Evidencia</th>"
                         "<th>Instrumento</th></tr>%s</table>" % "".join(
                             "<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (e(x["cuando"]), e(x["evidencia"]), e(x["instrumento"]))
                             for x in syl["evaluacion"]))
        if syl.get("infraestructura"):
            guide.append("<h4>Prepara tu entorno</h4><p>%s</p>" % e(syl["infraestructura"]))
        guide.append("<h4>Acuerdos pedagógicos</h4><ul><li>Participa activamente y respeta la etiqueta en los "
                     "encuentros virtuales.</li><li>Entrega en las fechas del cronograma.</li><li>Usa el tutor IA "
                     "para aprender, no para que haga tus entregables.</li></ul>")
        Lesson.create({"section_id": intro.id, "sequence": 1, "lesson_type": "lectura", "duration_min": 20,
                       "name": "Guía del estudiante", "summary": "Cómo funciona el curso, ruta, evaluación y acuerdos.",
                       "content": "".join(guide)})
        if cert:
            info = (research or {}).get("certificacion") or {}
            ruta = ["<h4>%s</h4><p>%s · Código %s</p>" % (e(cert.name), e(cert.provider or ""), e(cert.exam_code or ""))]
            if info:
                ruta.append("<ul><li>Versión / estado: %s</li><li>Preguntas: %s · Duración: %s min</li>"
                            "<li>Aprobación: %s</li><li>Precio: %s</li><li>Idiomas: %s</li></ul>" % tuple(
                                e(str(info.get(k) or "—")) for k in ("estado", "preguntas", "duracion_min",
                                                                       "puntaje_aprobacion", "precio", "idiomas")))
            if cert.domain_ids:
                ruta.append("<h4>Dominios del examen</h4><table class='table'><tr><th>Dominio</th><th>Peso</th></tr>%s</table>" % "".join(
                    "<tr><td>%s</td><td>%s %%</td></tr>" % (e(d.name), d.weight) for d in cert.domain_ids))
            ruta.append("<h4>Cómo te prepara este curso</h4><ul><li>Cada núcleo cubre uno o más dominios.</li>"
                        "<li>El simulador reproduce el examen con preguntas por dominio y cronómetro.</li>"
                        "<li>Para la microcredencial: 100 %% de lecciones y simulador con %s %% o más.</li></ul>" % int(cert.passing_score or 70))
            if cert.verify_note:
                ruta.append("<p class='cp-small'>ℹ️ %s</p>" % e(cert.verify_note))
            if cert.url:
                ruta.append("<p><a href='%s' target='_blank'>Página oficial de la certificación ↗</a></p>" % e(cert.url))
            Lesson.create({"section_id": intro.id, "sequence": 2, "lesson_type": "lectura", "duration_min": 20,
                           "name": "Ruta de certificación internacional",
                           "summary": "Qué examen presentarás, cómo se registra y cómo te prepara el simulador.",
                           "content": "".join(ruta)})
        Lesson.create({"section_id": intro.id, "sequence": 3, "lesson_type": "quiz", "duration_min": 20,
                       "name": "Cuestionario diagnóstico inicial",
                       "summary": "Mide tus saberes previos; el tutor IA lo usa para personalizar tu ruta.",
                       "content": "<p>Responde sin consultar: no afecta tu nota.</p>"})
        Lesson.create({"section_id": intro.id, "sequence": 4, "lesson_type": "video", "duration_min": 10,
                       "name": "Video de bienvenida", "summary": "Presentación del curso y de la ruta hacia la certificación.",
                       "content": False, "video_query": "%s %s" % (course.name, cert.exam_code if cert else "")})
        Lesson.create({"section_id": close.id, "sequence": 1, "lesson_type": "actividad", "duration_min": 20,
                       "name": "Autoevaluación", "summary": "Reflexión guiada sobre tu proceso y logros.",
                       "content": False})
        Lesson.create({"section_id": close.id, "sequence": 2, "lesson_type": "quiz", "duration_min": 60,
                       "name": "Simulacro de certificación",
                       "summary": "Presenta el simulador en condiciones reales de tiempo. Necesitas el puntaje mínimo para tu microcredencial.",
                       "content": "<p>Ve a la pestaña <b>Simulador de certificación</b> y presenta el simulacro completo.</p>"})
        Lesson.create({"section_id": close.id, "sequence": 3, "lesson_type": "sesion_virtual", "duration_min": 60,
                       "name": "Plan para presentar el examen oficial",
                       "summary": "Sesión de cierre: inscripción al examen, últimos repasos y recomendaciones.",
                       "session_datetime": datetime.combine((close.date_end or fields.Date.today()), time(0, 0)),
                       "ai_guide": "<ul><li>Revisión del resultado por dominio del simulacro.</li>"
                                   "<li>Plan de repaso de 2 semanas.</li><li>Proceso de inscripción y políticas del examen.</li></ul>"})

    # ------------------------------------------------------------- fuentes
    def _sources_html(self, syl, research, cert):
        e = html_escape
        out = []
        if syl.get("bibliografia"):
            out.append("<h4>Bibliografía del syllabus</h4><ul>%s</ul>" % "".join(
                "<li>%s</li>" % e(b) for b in syl["bibliografia"]))
        if (research or {}).get("bibliografia"):
            out.append("<h4>Bibliografía actualizada (investigación del agente)</h4><ul>%s</ul>" % "".join(
                "<li>%s</li>" % e(b) for b in research["bibliografia"]))
        links = []
        for c in syl.get("cibergrafia") or []:
            links.append(_linkify(e(c)))
        if cert and cert.url:
            links.append("<a href='%s' target='_blank'>%s – página oficial</a>" % (e(cert.url), e(cert.name)))
        for n in (research or {}).get("nucleos") or []:
            for r in n.get("recursos") or []:
                if (r.get("url") or "").startswith("http"):
                    links.append("<a href='%s' target='_blank'>%s</a> <small>(%s)</small>" % (
                        e(r["url"]), e(r.get("titulo") or r["url"]), e(r.get("tipo") or "recurso")))
        seen, uniq = set(), []
        for l in links:
            if l not in seen:
                seen.add(l)
                uniq.append(l)
        if uniq:
            out.append("<h4>Cibergrafía y recursos</h4><ul>%s</ul>" % "".join("<li>%s</li>" % l for l in uniq))
        consulted = (research or {}).get("_sources") or []
        if consulted:
            out.append("<h4>Fuentes consultadas por el agente (%s)</h4><ul>%s</ul>" % (
                fields.Date.today(), "".join("<li><a href='%s' target='_blank'>%s</a></li>" % (
                    e(s["url"]), e(s.get("title") or s["url"])) for s in consulted[:40])))
        return "".join(out) or False


def _linkify(text):
    return re.sub(r"(https?://[^\s<]+)", r"<a href='\1' target='_blank'>\1</a>", text)


def _rubric(criterios):
    if not criterios:
        return ""
    rows = "".join("<tr><td>%s</td><td>Cumple totalmente con evidencia clara.</td><td>Cumple parcialmente.</td>"
                   "<td>No cumple.</td></tr>" % html_escape(c) for c in criterios)
    return ("<h4>Rúbrica</h4><table class='table'><tr><th>Criterio</th><th>BUENO (100 %)</th><th>REGULAR (60 %)</th>"
            "<th>INSUFICIENTE (0 %)</th></tr>" + rows + "</table>")


def _num(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return 4.0


def _bib_html(bib):
    e = html_escape
    out = []
    if bib.get("principal"):
        out.append("<h4>Libro guía</h4><table class='table'><tr><th>Libro</th><th>Autor</th><th>Tema</th><th>Qué leer</th></tr>%s</table>" % "".join(
            "<tr><td>%s%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                ("<a href='%s' target='_blank'>%s</a>" % (e(b["url"]), e(b["titulo"]))) if b.get("url", "").startswith("http") else e(b["titulo"]),
                ("<br/><small>%s</small>" % e(b["referencia"])) if b.get("referencia") else "",
                e(b.get("autor")), e(b.get("tema")), e(b.get("paginas"))) for b in bib["principal"]))
    if bib.get("complementaria"):
        out.append("<h4>Material de apoyo complementario</h4><ul>%s</ul>" % "".join(
            "<li>%s <small>— %s</small></li>" % (
                ("<a href='%s' target='_blank'>%s</a>" % (e(b["url"]), e(b["titulo"]))) if b.get("url", "").startswith("http") else e(b["titulo"]),
                e(b.get("autor") or b.get("referencia") or "")) for b in bib["complementaria"]))
    return "".join(out)


def _clean_slides(slides):
    out = []
    for s in slides or []:
        if not isinstance(s, dict) or not s.get("title"):
            continue
        pts = [str(x)[:300] for x in (s.get("points") or []) if x][:6]
        out.append({"title": str(s["title"])[:120], "lead": str(s.get("lead") or "")[:160], "points": pts})
    return out[:12] or False
