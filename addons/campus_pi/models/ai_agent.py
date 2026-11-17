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

from ..tools import llm

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import html2plaintext, html_escape

_logger = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-5-5"
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def call_messages(conf, system, messages, max_tokens=2000, temperature=0.4, tools=None, timeout=300,
                  json_mode=False):
    """Llama al proveedor configurado (Claude, Gemini, Groq, ChatGPT o compatible). Devuelve
    (texto, fuentes, stop). ``tools`` verdadero = usar búsqueda web si el proveedor la ofrece.
    No usa el ORM: puede ejecutarse en hilos paralelos."""
    try:
        return llm.call(conf, system, messages, max_tokens=max_tokens, temperature=temperature,
                        web_search=bool(tools), json_mode=json_mode, timeout=timeout)
    except llm.LLMError as e:
        raise UserError(str(e))


class CampusAiAgent(models.AbstractModel):
    _name = "campus.ai.agent"
    _description = "Agentes de IA del campus"

    # ------------------------------------------------------------------ LLM
    # ------------------------------------------------- configuración del proveedor
    KEY_PARAMS = {"anthropic": ("ANTHROPIC_API_KEY", "campus_pi.anthropic_api_key"),
                  "gemini": ("GEMINI_API_KEY", "campus_pi.gemini_api_key"),
                  "groq": ("GROQ_API_KEY", "campus_pi.groq_api_key"),
                  "openai": ("OPENAI_API_KEY", "campus_pi.openai_api_key"),
                  "compatible": ("AI_API_KEY", "campus_pi.compatible_api_key")}

    @api.model
    def _param(self, env_name, param):
        return (os.environ.get(env_name) or self.env["ir.config_parameter"].sudo().get_param(param) or "").strip()

    @api.model
    def _key_for(self, provider):
        env_name, param = self.KEY_PARAMS[provider]
        key = self._param(env_name, param)
        if provider == "anthropic" and not key.startswith("sk-ant-"):
            return ""  # evita fallos con valores como "pendiente"
        if provider == "compatible" and not key and self.env["ir.config_parameter"].sudo().get_param("campus_pi.ai_base_url"):
            return "local"  # Ollama / LM Studio no requieren clave
        return key if len(key) >= 8 or provider == "compatible" else ""

    @api.model
    def _provider(self):
        wanted = self._param("AI_PROVIDER", "campus_pi.ai_provider").lower()
        if wanted in self.KEY_PARAMS and self._key_for(wanted):
            return wanted
        for prov in ("anthropic", "gemini", "groq", "openai", "compatible"):
            if self._key_for(prov):
                return prov
        return ""

    @api.model
    def _api_key(self):
        prov = self._provider()
        return self._key_for(prov) if prov else ""

    @api.model
    def is_enabled(self):
        return bool(self._provider())

    @api.model
    def _api_url(self):
        prov = self._provider()
        custom = self._param("CAMPUS_ANTHROPIC_URL", "campus_pi.anthropic_url") if prov == "anthropic" else ""
        db_url = self.env["ir.config_parameter"].sudo().get_param("campus_pi.ai_base_url") if prov == "compatible" else ""
        return custom or os.environ.get("AI_BASE_URL") or db_url or llm.PROVIDERS.get(prov, {}).get("url", "")

    @api.model
    def _model(self):
        prov = self._provider()
        model = self._param("AI_MODEL", "campus_pi.ai_model")
        if prov == "anthropic":
            model = model or self._param("CLAUDE_MODEL", "campus_pi.claude_model")
        return model or llm.PROVIDERS.get(prov, {}).get("model", "")

    @api.model
    def _llm_conf(self):
        """Configuración para llamar al modelo sin tocar la base de datos (apta para hilos)."""
        prov = self._provider()
        return {"provider": prov, "key": self._key_for(prov) if prov else "", "url": self._api_url(),
                "model": self._model()}

    BULK_MODELS = {"anthropic": "claude-haiku-5-5", "openai": "gpt-4o-mini"}

    @api.model
    def bulk_conf(self):
        """Configuración económica para generar o regenerar cursos completos: modelo más barato del mismo
        proveedor (Claude Haiku en lugar de Sonnet). Se puede fijar otro en el parámetro campus_pi.ai_bulk_model."""
        conf = dict(self._llm_conf())
        model = self.env["ir.config_parameter"].sudo().get_param("campus_pi.ai_bulk_model") or \
            self.BULK_MODELS.get(conf["provider"])
        if model and conf["provider"] != "compatible":
            conf["model"] = model
        return conf

    @api.model
    def provider_label(self):
        conf = self._llm_conf()
        return llm.label(conf) if conf["provider"] else "Sin IA"

    @api.model
    def has_web_search(self):
        prov = self._provider()
        return bool(prov and llm.PROVIDERS[prov]["search"])

    @api.model
    def _messages(self, system, messages, max_tokens=2000, temperature=0.4, tools=None, timeout=300, json_mode=False):
        conf = self._llm_conf()
        out = call_messages(conf, system, messages, max_tokens, temperature, tools, timeout, json_mode)
        self._remember_model(conf)
        return out

    @api.model
    def _remember_model(self, conf):
        """Si el modelo configurado fue retirado y se resolvió otro, se guarda para las próximas llamadas."""
        if conf.get("resolved_model"):
            ICP = self.env["ir.config_parameter"].sudo()
            ICP.set_param("campus_pi.ai_model", conf["resolved_model"])
            if conf.get("provider") == "anthropic":
                ICP.set_param("campus_pi.claude_model", conf["resolved_model"])
            _logger.warning("Modelo de IA actualizado automáticamente a %s", conf["resolved_model"])

    @api.model
    def _call(self, system, messages, max_tokens=2000, temperature=0.4, json_mode=False):
        return self._messages(system, messages, max_tokens=max_tokens, temperature=temperature, json_mode=json_mode)[0]

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
        data = self._json(self._call(self.STRUCTURE_SYSTEM, [{"role": "user", "content": prompt}], 6000, 0.0, json_mode=True))
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
        search = self.has_web_search()
        if not search:
            prompt += ("\n\nNOTA: en este proveedor no tienes búsqueda web. Usa tu conocimiento, no inventes URL "
                       "que no conozcas con certeza y agrega en «advertencias» que los datos deben verificarse en "
                       "las páginas oficiales.")
        text, sources, _stop = self._messages(self.RESEARCH_SYSTEM, [{"role": "user", "content": prompt}],
                                              max_tokens=8000, tools=search, timeout=420, json_mode=not search)
        data = self._json(text)
        if not isinstance(data, dict):
            data = {}
        data["_sources"] = sources
        return data

    # ----------------------------------------------- contenido por núcleo
    NUCLEO_SYSTEM = """Eres el Agente de Diseño Instruccional de InnovaTech Lab del Politécnico Internacional (Colombia).
Desarrollas los materiales de UN núcleo de un curso virtual a partir del syllabus institucional (PI-GA-FT-141),
respetando su objetivo, temas, estrategias y criterios de evaluación, y alineándolo con la certificación
internacional objetivo y con la investigación verificada que se te entrega.
Sigues los formatos de la Unidad Virtual del Politécnico: lectura del núcleo (presentación, «Lo que lograrás»,
secciones numeradas con tablas, código y recuadros, buenas prácticas, casos para reflexionar, glosario y
referencias APA 7), recursos bibliográficos (libro guía y material complementario), infografía (pregunta
orientadora, texto orientador de máximo 300 caracteres y 10-14 términos clave) y caso integrador con rúbrica
(BUENO 100 %, REGULAR 60 %, INSUFICIENTE 0 %).
Escribes en español de Colombia, en un tono cercano y profesional (tuteo), riguroso y con ejemplos de una
organización colombiana ficticia que se usa como hilo conductor. Nunca inventas URL ni referencias: usa solo
las de la investigación o del syllabus. Respondes SOLO con JSON válido, sin texto adicional."""

    MEDIA_SYSTEM = """Eres el guionista y diseñador de presentaciones de InnovaTech Lab del Politécnico Internacional.
Conviertes un núcleo de un curso en un video explicativo por escenas (cada escena es una diapositiva con lo que
se ve en pantalla y lo que dice el docente) y en una actividad interactiva tipo VideoQuiz (H5P).

DISEÑO DE LAS DIAPOSITIVAS (estilo institucional, sobrio y profesional):
- Pocas palabras en pantalla: 2-5 frases cortas por escena, nunca párrafos. Nada de emojis.
- Varía los formatos: portada (primera), puntos con ícono, código, tabla comparativa, proceso por pasos,
  comparación (bien/mal), cita o idea clave, y cierre (última).
- Usa código real y correcto cuando el tema sea técnico; usa tablas para comparar; usa proceso para secuencias.

REGLAS DE VOZ (la narración la lee una voz neuronal y debe sonar humana, no robótica):
- Habla como un docente en clase, de tú a tú: frases cortas (máx. 22 palabras), conectores naturales
  («fíjate en», «ahora bien», «piénsalo así», «por ejemplo»), una analogía o un ejemplo del caso por escena.
- No leas las viñetas: explícalas y agrega lo que no está en pantalla.
- Escribe los símbolos como se pronuncian: @Valid → «arroba Valid», application/json → «application barra json»,
  .properties → «punto properties», 404 → «cuatrocientos cuatro», 25 % → «veinticinco por ciento».
- Sin URL, sin markdown, sin paréntesis largos ni listas dentro de la narración. Explica las siglas la primera vez.
- La primera escena da la bienvenida y presenta la ruta; la última resume y anuncia lo que sigue.

ACTIVIDAD: preguntas tipo caso (situación concreta + decisión), 4 opciones plausibles, 1 correcta y
retroalimentación que explique el porqué de cada opción. Indica después de qué escena aparece cada una.
Respondes SOLO con JSON válido, sin texto adicional."""

    def _nucleo_prompt_head(self, nuc, cert_info, research, instructions, summary, material=None):
        rn = next((x for x in (research or {}).get("nucleos") or [] if x.get("numero") == nuc["numero"]), {})
        cert_txt = "Ninguna"
        if cert_info:
            cert_txt = "%s (%s, %s). Dominios: %s" % (cert_info["name"], cert_info["provider"], cert_info["code"],
                                                       "; ".join("%s %s%%" % d for d in cert_info["domains"]))
        return (
            "NÚCLEO %s – %s\nObjetivo: %s\nTemas: %s\nEstrategias: %s\nCriterios de evaluación: %s\n\n"
            "CERTIFICACIÓN: %s\nINVESTIGACIÓN VERIFICADA PARA ESTE NÚCLEO: %s\n"
            "INSTRUCCIONES DEL ADMINISTRADOR: %s\n\nSYLLABUS COMPLETO (contexto):\n%s\n\n") % (
            nuc["numero"], nuc["titulo"], nuc.get("objetivo") or "-", "; ".join(nuc.get("temas") or []) or "-",
            "; ".join(nuc.get("estrategias") or []) or "-", " ".join(nuc.get("criterios") or []) or "-",
            cert_txt, json.dumps(rn, ensure_ascii=False)[:5000] or "-", instructions or "-", summary[:9000]) + (
            ("MATERIAL DEL DOCENTE PARA ESTE NÚCLEO (fuente PRIORITARIA: respeta sus explicaciones, ejemplos, caso, "
             "código y terminología; complétalo y llévalo al formato institucional, no lo contradigas; si trae una "
             "lectura, un guion o un caso, mejóralos en lugar de reemplazarlos por otros):\n%s\n\n") % material
            if material else "")

    def _json_call(self, conf, system, prompt, label, max_tokens=16000, retry_hint=""):
        last = None
        for attempt in range(2):
            msgs = [{"role": "user", "content": prompt + (
                "\n\nIMPORTANTE: la respuesta anterior no fue JSON válido o quedó incompleta; %s" % retry_hint
                if attempt else "")}]
            text, _src, stop = call_messages(conf, system, msgs, max_tokens=max_tokens, temperature=0.5,
                                             timeout=600, json_mode=True)
            try:
                data = self._json(text)
                if isinstance(data, dict):
                    return data
            except ValueError as e:
                last = e
        raise UserError("Respuesta inválida del modelo para %s (%s)" % (label, last))

    @api.model
    def nucleo_content_payload(self, summary, nuc, cert_info, research, instructions=None, conf=None, with_case=True,
                               material=None):
        """Lectura, bibliografía, infografía, caso, sesiones y preguntas. No usa la BD si se pasa ``conf``."""
        from .agent_job import NUCLEO_SCHEMA
        from ..tools.visual import ICON_NAMES
        conf = conf or self._llm_conf()
        prompt = self._nucleo_prompt_head(nuc, cert_info, research, instructions, summary, material) + (
            "Requisitos: lectura de 1200-1600 palabras en secciones numeradas, con al menos una tabla, ejemplos "
            "(código real si el tema es técnico) y 1-2 recuadros; 3 casos para reflexionar; glosario; referencias APA. "
            "Bibliografía: 1-2 libros guía (prefiere libros de acceso libre o de E-libro) con capítulos o páginas a "
            "consultar, y 4-8 recursos complementarios oficiales. Infografía de 10-14 términos. %s"
            "Laboratorio práctico con pasos (o null si el núcleo no lo admite); agenda de la sesión virtual de 90 min; "
            "guion del agente IA para la sesión presencial (diagnóstico, preguntas detonantes, reto práctico, cierre); "
            "6 preguntas tipo examen de opción múltiple (4 opciones, 1 correcta, retroalimentación por opción) con el "
            "nombre exacto del dominio de la certificación.\nICONOS disponibles: %s\nEsquema JSON exacto:\n%s") % (
            ("Caso integrador: historia, indicaciones numeradas, entregables, tabla de solución para el docente y "
             "rúbrica de 4 criterios que suman 5,0 según los criterios de evaluación del syllabus. ") if with_case
            else "El campo «caso» va en null. ", ", ".join(ICON_NAMES), NUCLEO_SCHEMA)
        data = self._json_call(conf, self.NUCLEO_SYSTEM, prompt, "el núcleo %s" % nuc["numero"],
                               retry_hint="sé más conciso (lectura de máximo 900 palabras).")
        if not data.get("lectura"):
            raise UserError("El modelo no devolvió la lectura del núcleo %s" % nuc["numero"])
        return data

    @api.model
    def nucleo_media_payload(self, summary, nuc, cert_info, research, instructions=None, conf=None, course_name="",
                             material=None, economy=False):
        """Escenas del video/presentación con narración natural y actividad interactiva (H5P)."""
        from .agent_job import MEDIA_SCHEMA
        from ..tools.visual import ICON_NAMES
        conf = conf or self._llm_conf()
        prompt = self._nucleo_prompt_head(nuc, cert_info, research, instructions, summary,
                                          (material or "")[:8000] or None) + (
            "CURSO: %s\nCrea el video explicativo del núcleo (%s escenas, unos %s minutos en total a 145 palabras por "
            "minuto) y la actividad interactiva (%s preguntas tipo caso repartidas a lo largo del video).\n"
            "ICONOS disponibles: %s\nEsquema JSON exacto:\n%s") % (
            course_name or "-", "9-11" if economy else "12-16", 12 if economy else 18, "8" if economy else "10-15",
            ", ".join(ICON_NAMES), MEDIA_SCHEMA)
        data = self._json_call(conf, self.MEDIA_SYSTEM, prompt, "el video del núcleo %s" % nuc["numero"],
                               max_tokens=14000, retry_hint="usa 10 escenas de máximo 110 palabras y 8 preguntas.")
        if not data.get("escenas"):
            raise UserError("El modelo no devolvió escenas para el núcleo %s" % nuc["numero"])
        return data

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
        prompt = prompt.replace("Responde SOLO un JSON: [", "Responde SOLO un JSON: {\"questions\": [").replace(
            "\"feedback\": str}]}]", "\"feedback\": str}]}]}")
        data = self._json(self._call(self.NUCLEO_SYSTEM, [{"role": "user", "content": prompt}], 12000, json_mode=True))
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
    def course_insights(self, course):
        """Dificultades del grupo: promedio por dominio en los simulacros y últimas preguntas al tutor."""
        attempts = self.env["campus.sim.attempt"].sudo().search([("course_id", "=", course.id), ("state", "=", "done")])
        acc = {}
        for a in attempts:
            for dom, r in (a.domain_report or {}).items():
                tot = acc.setdefault(dom, [0, 0])
                tot[0] += r.get("ok", 0)
                tot[1] += r.get("total", 0)
        domains = sorted(((d, round(100.0 * v[0] / v[1], 1)) for d, v in acc.items() if v[1]), key=lambda x: x[1])
        students = course.enrollment_ids.mapped("user_id")
        asked = self.env["campus.ai.message"].sudo().search([
            ("course_id", "=", course.id), ("role", "=", "user"), ("user_id", "in", students.ids)],
            order="id desc", limit=12)
        return {"attempts": len(attempts), "domains": domains,
                "questions": [(m.user_id.name, m.content[:220], m.create_date) for m in asked]}

    TUTOR_STUDENT = (
        "Eres el Tutor IA de InnovaTech Lab (Politécnico Internacional). Acompañas a %s, estudiante del curso. "
        "Responde EXACTAMENTE lo que pregunta en su último mensaje: si pide una explicación, explica ese tema; "
        "si pide preguntas, formula preguntas nuevas; nunca repitas una respuesta anterior. Explica con ejemplos "
        "colombianos cotidianos, cita la lección del curso relacionada cuando exista y termina con una pregunta de "
        "verificación o un mini-reto. No entregues resuelto un entregable calificable: guía paso a paso. Si la "
        "pregunta no está en el contenido del curso, respóndela con tu conocimiento y dilo. Español, máximo 250 "
        "palabras, Markdown sencillo.\nDominios más débiles del estudiante en su último simulacro: %s")
    TUTOR_TEACHER = (
        "Eres el Asistente IA del %s del curso en InnovaTech Lab (Politécnico Internacional). Hablas con %s. "
        "Respondes EXACTAMENTE a su solicitud: preparar sesiones (agenda, actividades, preguntas detonantes), "
        "explicar un tema con profundidad para enseñarlo, redactar preguntas tipo examen con respuesta correcta y "
        "retroalimentación, rúbricas, casos y analizar en qué tienen dificultades los estudiantes. Puedes dar "
        "respuestas completas (no aplica el método socrático). Nunca repitas una respuesta anterior. Español, "
        "Markdown sencillo, máximo 450 palabras salvo que pida un material más largo.\nDIFICULTADES DEL GRUPO: %s")

    @api.model
    def tutor_reply(self, course, user, message):
        Msg = self.env["campus.ai.message"].sudo()
        Msg.create({"user_id": user.id, "course_id": course.id, "role": "user", "content": message})
        enrollment = course.enrollment_ids.filtered(lambda e: e.user_id == user)[:1]
        role = user.campus_role
        staff = role in ("admin", "teacher")
        if not self.is_enabled():
            answer = self._offline_answer(course, message, enrollment, staff)
        else:
            if staff:
                ins = self.course_insights(course)
                diff = "Simulacros presentados: %s. Promedio por dominio (de menor a mayor): %s. Últimas preguntas de los " \
                       "estudiantes al tutor: %s" % (
                           ins["attempts"], "; ".join("%s %s%%" % d for d in ins["domains"]) or "sin datos",
                           " | ".join(q[1] for q in ins["questions"][:8]) or "sin datos")
                system = self.TUTOR_TEACHER % ("administrador" if role == "admin" else "docente", user.name, diff)
            else:
                weak = self._weak_domains(enrollment) if enrollment else []
                system = self.TUTOR_STUDENT % (
                    user.name, ", ".join("%s (%s%%)" % (d, r.get("pct")) for d, r in weak) or "sin datos")
            system += "\n\nCONTEXTO DEL CURSO:\n%s\n\nINSTRUCCIONES DEL DOCENTE: %s" % (
                self._course_context(course), course.tutor_prompt or "-")
            history = Msg.search([("user_id", "=", user.id), ("course_id", "=", course.id)], order="id desc", limit=12)
            msgs = [{"role": m.role, "content": m.content} for m in reversed(history)]
            try:
                answer = self._call(system, msgs, max_tokens=1600 if staff else 900, temperature=0.6)
                if not answer.strip():
                    raise UserError("respuesta vacía")
            except UserError as e:
                answer = "⚠️ La IA no está disponible en este momento (%s).\n\n" % e.args[0][:160] + \
                         self._offline_answer(course, message, enrollment, staff)
        Msg.create({"user_id": user.id, "course_id": course.id, "role": "assistant", "content": answer})
        return answer

    STOP = set("para como cual cuales donde desde entre sobre porque pero tambien este esta estos estas tiene tienen "
               "puede pueden hacer explicame explica dime quiero necesito ayuda sobre tema temas curso favor seria "
               "cuando quien".split())

    def _terms(self, text):
        import unicodedata
        t = unicodedata.normalize("NFD", (text or "").lower())
        t = "".join(c for c in t if unicodedata.category(c) != "Mn")
        return [w[:7] for w in re.findall(r"[a-z0-9+#]{4,}", t) if w not in self.STOP]

    def _offline_answer(self, course, message, enrollment=None, staff=False):
        """Respuesta sin IA: busca en el contenido del curso los fragmentos que responden la pregunta."""
        import random
        msg = (message or "").lower()
        rnd = random.Random()
        if re.search(r"pregunta|examen|quiz|evalúa|evaluame|evalúame|practicar", msg):
            qs = course.question_ids.filtered(lambda q: len(q.option_ids) >= 2)
            terms = set(self._terms(message))
            ranked = sorted(qs, key=lambda q: -len(terms & set(self._terms(q.name + " " + (q.domain or "")))))
            pool = ranked[:12] if terms else list(qs)
            pick = rnd.sample(list(pool), min(3, len(pool))) if pool else []
            if pick:
                out = ["(Modo sin IA) Practica con estas preguntas del banco del curso:"]
                for i, q in enumerate(pick, 1):
                    out.append("\n**%d. %s**" % (i, q.name))
                    out += ["- %s) %s" % ("ABCD"[k] if k < 4 else k + 1, o.name) for k, o in enumerate(q.option_ids)]
                    if staff:
                        good = q.option_ids.filtered("is_correct")[:1]
                        out.append("  ✔ Respuesta: %s. %s" % (good.name, q.explanation or ""))
                if not staff:
                    out.append("\nResponde con la letra de cada una y te digo cómo te fue (o preséntalas en el simulador).")
                return "\n".join(out)
        if re.search(r"domini|reforz|débil|debil|cuesta", msg):
            if staff:
                ins = self.course_insights(course)
                if ins["domains"]:
                    return "(Modo sin IA) Promedio del grupo por dominio en %s simulacros:\n%s" % (
                        ins["attempts"], "\n".join("- **%s**: %s %%" % d for d in ins["domains"]))
            elif enrollment:
                weak = self._weak_domains(enrollment)
                if weak:
                    return "(Modo sin IA) Según tu último simulacro, refuerza:\n%s" % "\n".join(
                        "- **%s**: %s %%" % (d, r.get("pct")) for d, r in weak)
        m_n = re.search(r"n[uú]cleo\s*(\d+)", msg)
        if m_n:
            sec = course.section_ids.filtered(lambda x: re.match(r"(?i)\s*n[úu]cleo\s+%s\b" % m_n.group(1), x.name or ""))[:1]
            if sec:
                lect = sec.lesson_ids.filtered(lambda l: l.lesson_type == "lectura")[:1]
                heads = re.findall(r"<h4[^>]*>(.*?)</h4>", lect.content or "")[:6] if lect else []
                out = ["(Modo sin IA) **%s**" % sec.name]
                if sec.objective:
                    out.append("**Objetivo:** %s" % sec.objective)
                if heads:
                    out.append("**Ideas clave para explicar:**\n" + "\n".join("- %s" % html2plaintext(h).strip() for h in heads))
                out.append("**Ruta del núcleo:**\n" + "\n".join("- %s (%s min)" % (l.name, l.duration_min) for l in sec.lesson_ids))
                if staff:
                    out.append("Sugerencia: inicia con una pregunta detonante sobre un caso real, explica las ideas clave "
                               "con la presentación del núcleo y cierra con 3 preguntas del banco.")
                return "\n\n".join(out)
        terms = self._terms(message)
        if not terms:
            return "(Modo sin IA) Cuéntame con más detalle qué tema del curso quieres trabajar."
        scored = []
        for l in course.lesson_ids:
            text = html2plaintext(l.content or "") + " " + html2plaintext(l.ai_guide or "")
            for sent in re.split(r"(?<=[.!?:])\s+|\n+", text):
                sent = sent.strip(" *-•")
                if len(sent) < 40 or len(sent) > 600:
                    continue
                st = set(self._terms(sent))
                score = sum(1 for w in set(terms) if w in st) + 0.3 * sum(1 for w in set(self._terms(l.name)) if w in terms)
                if score >= 1:
                    scored.append((score + rnd.random() * 0.01, sent, l))
        scored.sort(key=lambda x: -x[0])
        if not scored:
            return ("(Modo sin IA) No encontré ese tema en el contenido del curso. Reformula la pregunta con otras "
                    "palabras o agenda una tutoría con tu docente.")
        seen, out = set(), []
        for _sc, sent, l in scored:
            if sent in seen:
                continue
            seen.add(sent)
            out.append("- %s _(%s)_" % (sent, l.name))
            if len(out) == 4:
                break
        return "(Modo sin IA) Esto dice el curso sobre tu pregunta:\n%s\n\n¿Quieres que te haga preguntas de práctica sobre este tema?" % "\n".join(out)

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
