# -*- coding: utf-8 -*-
"""Material del curso aportado por el docente (opcional) y regeneración de cursos con los agentes."""
import base64
import logging
import os
import re
import threading

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

from ..tools import material as mat_tools

_logger = logging.getLogger(__name__)


class CampusMaterial(models.Model):
    _name = "campus.material"
    _description = "Material del curso aportado por el docente"
    _order = "nucleo, id"

    name = fields.Char("Nombre del archivo", required=True)
    path = fields.Char("Ruta (dentro del comprimido)")
    job_id = fields.Many2one("campus.agent.job", "Ejecución del agente", ondelete="cascade", index=True)
    course_id = fields.Many2one("campus.course", "Curso", ondelete="cascade", index=True)
    lesson_id = fields.Many2one("campus.lesson", "Lección donde se publicó", ondelete="set null")
    nucleo = fields.Integer("Núcleo", help="0 = material general del curso")
    kind = fields.Selection([(k, v) for k, v in mat_tools.KIND_LABELS.items()], "Tipo", default="otro")
    size = fields.Integer("Tamaño (bytes)")
    file = fields.Binary("Archivo", attachment=True)
    text = fields.Text("Texto extraído")
    state = fields.Selection([("new", "Por procesar"), ("done", "Procesado")], default="new")

    def _expand(self):
        """Descomprime los .zip y extrae el texto de cada archivo (lo ejecuta el agente)."""
        out = self.browse()
        for m in self.filtered(lambda x: x.state == "new"):
            if not m.file:
                m.state = "done"
                out |= m
                continue
            raw = base64.b64decode(m.file or b"")
            parts = mat_tools.unpack(raw, m.name)
            if len(parts) == 1 and parts[0][0] == m.name:
                txt = mat_tools.extract(raw, m.name)
                m.write({"text": (txt or "")[:mat_tools.MAX_TEXT], "kind": mat_tools.kind_of(m.name), "state": "done",
                         "nucleo": m.nucleo or mat_tools.detect_nucleo(m.path or m.name, txt), "size": len(raw)})
                out |= m
                continue
            for path, data in parts:
                base = os.path.basename(path)
                txt = mat_tools.extract(data, base) if data else "[Archivo demasiado grande dentro del comprimido]"
                out |= self.create({
                    "name": base, "path": "%s/%s" % (m.name, path), "job_id": m.job_id.id, "course_id": m.course_id.id,
                    "nucleo": m.nucleo or mat_tools.detect_nucleo(path, txt), "kind": mat_tools.kind_of(base),
                    "size": len(data or b""), "file": base64.b64encode(data) if data else False,
                    "text": (txt or "")[:mat_tools.MAX_TEXT], "state": "done"})
            m.unlink()  # el comprimido ya quedó desempacado
        return out | self.exists().filtered(lambda x: x.state == "done")


class CampusAgentJobMaterial(models.Model):
    _inherit = "campus.agent.job"

    material_ids = fields.One2many("campus.material", "job_id", "Material del curso")
    roster_students = fields.Binary("Hoja de estudiantes", attachment=True)
    roster_students_name = fields.Char()
    roster_teachers = fields.Binary("Hoja de docentes", attachment=True)
    roster_teachers_name = fields.Char()
    economy = fields.Boolean("Modo económico", help="Modelo más barato y sin investigación web (regeneraciones).")
    regenerate_course_id = fields.Many2one("campus.course", "Curso que se regenera", ondelete="set null")

    def add_materials(self, files):
        """files: [(nombre, bytes)] desde el formulario. Valida tamaños y los deja listos para el agente."""
        self.ensure_one()
        total = 0
        for name, data in files:
            if not data:
                continue
            if len(data) > mat_tools.MAX_FILE_MB * 1024 * 1024:
                raise UserError(_("«%s» supera %s MB. Para videos largos use un enlace de YouTube o Drive.") % (
                    name, mat_tools.MAX_FILE_MB))
            total += len(data)
            if total > mat_tools.MAX_TOTAL_MB * 1024 * 1024:
                raise UserError(_("El material supera %s MB en total.") % mat_tools.MAX_TOTAL_MB)
            self.env["campus.material"].sudo().create({
                "name": os.path.basename(name)[:200], "job_id": self.id, "size": len(data),
                "nucleo": mat_tools.detect_nucleo(name), "kind": mat_tools.kind_of(name),
                "file": base64.b64encode(data)})

    def _import_rosters(self, course):
        """Crea las cuentas de la hoja de estudiantes/docentes y las vincula al curso."""
        self.ensure_one()
        from ..tools import people as people_tools
        lines = []
        for field, role, label in (("roster_teachers", "teacher", "docentes"), ("roster_students", "student", "estudiantes")):
            if not self[field]:
                continue
            people, errs = people_tools.parse_people(base64.b64decode(self[field]), self[field + "_name"] or "lista.xlsx")
            res = self.env["campus.user.import"].sudo().import_people(people, role, course)
            new = sum(1 for r in res if r["status"].startswith("Creado"))
            warn = sum(1 for r in res if "falta el WhatsApp" in r["status"])
            lines.append("%s: %d procesados (%d cuentas nuevas con la contraseña Poli2026*)%s%s." % (
                label.capitalize(), len(res), new, ", %d filas con error" % len(errs) if errs else "",
                ", %d sin WhatsApp" % warn if warn else ""))
            self[field] = False
        return " ".join(lines)

    def _material_context(self, numero, limit=14000, general_limit=5000):
        """Texto del material para el prompt de un núcleo (no usa la BD en hilos: se calcula antes)."""
        mats = self.material_ids.filtered(lambda m: m.state == "done")
        own = mats.filtered(lambda m: m.nucleo == numero)
        gen = mats.filtered(lambda m: not m.nucleo)

        def block(recs, lim):
            out, used = [], 0
            for m in recs:
                txt = re.sub(r"\n{3,}", "\n\n", m.text or "").strip()
                head = "### %s (%s)" % (m.path or m.name, dict(self.env["campus.material"]._fields["kind"].selection).get(m.kind))
                if not txt:
                    txt = "[Archivo sin texto: %s. Úsalo como recurso de apoyo del núcleo.]" % m.name
                piece = "%s\n%s" % (head, txt[:max(lim - used, 0)])
                out.append(piece)
                used += len(piece)
                if used >= lim:
                    break
            return "\n\n".join(out)
        parts = []
        if own:
            parts.append(block(own, limit))
        if gen:
            parts.append(block(gen, general_limit))
        return "\n\n".join(p for p in parts if p)

    def _publish_materials(self, course):
        """Adjunta los archivos al curso: en su núcleo (o en Inicio) como «Material del docente».
        Una imagen o PDF llamado «infografía» reemplaza la infografía generada; un video, el video del núcleo."""
        self.ensure_one()
        Lesson = self.env["campus.lesson"].sudo()
        secs = {}
        for s in course.section_ids:
            if mat_tools.section_number(s.name):
                secs[mat_tools.section_number(s.name)] = s
        intro = course.section_ids.sorted("sequence")[:1]
        n = 0
        for m in self.material_ids.filtered(lambda x: x.file):
            m.course_id = course
            sec = secs.get(m.nucleo) or intro
            if not sec:
                continue
            low = m.name.lower()
            target = None
            if m.kind in ("imagen", "pdf") and "infograf" in low:
                target = sec.lesson_ids.filtered(lambda l: l.lesson_type == "infografia")[:1]
            elif m.kind == "multimedia" and low.endswith((".mp4", ".webm", ".mov")):
                target = sec.lesson_ids.filtered(lambda l: l.lesson_type == "video")[:1]
            if target:
                target.write({"attachment": m.file, "attachment_name": m.name})
            else:
                target = Lesson.create({
                    "section_id": sec.id, "sequence": 90 + n, "lesson_type": "lectura", "duration_min": 15,
                    "name": "Material del docente: %s" % m.name[:150],
                    "summary": "%s aportado por el docente%s." % (
                        mat_tools.KIND_LABELS.get(m.kind, "Archivo"), " (dentro de %s)" % m.path.split("/")[0] if m.path else ""),
                    "content": "<p>Archivo de apoyo del curso. Si no se ve en pantalla, descárgalo con el botón de la lección.</p>",
                    "attachment": m.file, "attachment_name": m.name})
                n += 1
            m.write({"lesson_id": target.id, "file": False})  # el archivo queda solo en la lección
        return n


class CampusCourseRegen(models.Model):
    _inherit = "campus.course"

    material_ids = fields.One2many("campus.material", "course_id", "Material del docente")

    def _syllabus_from_course(self):
        """Syllabus reconstruido a partir del curso (para regenerarlo con los agentes)."""
        self.ensure_one()
        from ..tools import syllabus as syl_tools
        syl = syl_tools.parse_text(self.syllabus_text) if self.syllabus_text else {}
        syl = dict(syl or {})
        nucleos, evaluacion = [], []
        for s in self.section_ids.sorted("sequence"):
            num = mat_tools.section_number(s.name)
            if not num:
                continue
            m = re.match(r"(?i)\s*n[úu]cleo\s+\d+\s*[–\-:.]?\s*(.*)", s.name or "")
            title = ((m.group(1) if m else "") or s.name).strip()
            temas = []
            for l in s.lesson_ids.filtered(lambda x: x.lesson_type == "lectura"):
                temas += [re.sub(r"^\s*\d+(\.\d+)*[.)]?\s*", "", html2plaintext(h)).strip()
                          for h in re.findall(r"<h[34][^>]*>(.*?)</h[34]>", l.content or "", re.S)]
            temas = [t for t in dict.fromkeys(temas) if 3 < len(t) < 120 and not re.match(
                r"(?i)(presentaci|fuentes|referencias|glosario|buenas pr|casos para|lo que lograr)", t)][:8]
            old = next((n for n in syl.get("nucleos") or [] if n.get("numero") == num), {})
            nucleos.append({"numero": num, "titulo": title, "objetivo": s.objective or old.get("objetivo") or "",
                            "temas": temas or old.get("temas") or [title], "estrategias": old.get("estrategias") or [],
                            "criterios": old.get("criterios") or []})
            if s.lesson_ids.filtered(lambda x: x.lesson_type == "caso"):
                evaluacion.append({"cuando": "Al finalizar el Núcleo %s" % num, "instrumento": "Proyecto con rúbrica",
                                   "evidencia": "Caso integrador", "criterios": [], "para_que": ""})
        syl["nucleos"] = nucleos or syl.get("nucleos") or []
        if evaluacion:
            syl["evaluacion"] = (syl.get("evaluacion") or []) + [e for e in evaluacion if not any(
                e["cuando"] == x.get("cuando") for x in syl.get("evaluacion") or [])]
        syl.setdefault("asignatura", self.name)
        if not syl.get("asignatura"):
            syl["asignatura"] = self.name
        if not syl.get("descripcion"):
            syl["descripcion"] = html2plaintext(self.description or "")
        if not syl.get("resultado_aprendizaje") and self.outcomes:
            syl["resultado_aprendizaje"] = html2plaintext(self.outcomes)[:600]
        if not syl.get("bibliografia") and self.sources_html:
            syl["bibliografia"] = [html2plaintext(x).strip() for x in re.findall(r"<li>(.*?)</li>", self.sources_html, re.S)][:12]
        syl["texto"] = (syl.get("texto") or self.syllabus_text or "")[:100000]
        for k in ("objetivos", "cibergrafia"):
            syl.setdefault(k, [])
        return syl

    def _current_content_materials(self, job):
        """El contenido actual de cada núcleo pasa como material del docente (no se pierde lo curado)."""
        Mat = self.env["campus.material"].sudo()
        for s in self.section_ids:
            num = mat_tools.section_number(s.name) or 0
            parts = []
            for l in s.lesson_ids:
                txt = html2plaintext(l.content or "").strip()
                if l.lesson_type in ("lectura", "caso", "laboratorio", "actividad") and len(txt) > 200 \
                        and not l.name.startswith("Material del docente"):
                    parts.append("## %s\n%s" % (l.name, txt))
                if l.attachment and l.attachment_name:
                    Mat.create({"name": l.attachment_name, "job_id": job.id, "nucleo": num,
                                "kind": mat_tools.kind_of(l.attachment_name), "file": l.attachment,
                                "size": len(base64.b64decode(l.attachment or b""))})
            if parts:
                Mat.create({"name": "Contenido actual – %s.txt" % (s.name or "sección")[:80], "job_id": job.id,
                            "nucleo": num, "kind": "texto", "text": "\n\n".join(parts)[:mat_tools.MAX_TEXT],
                            "state": "done"})
        for old in self.material_ids.filtered(lambda x: x.text):
            Mat.create({"name": old.name, "path": old.path, "job_id": job.id, "nucleo": old.nucleo, "kind": old.kind,
                        "text": old.text, "state": "done"})

    def action_regenerate(self, instructions=None, files=None, deep_research=False, start=True, economy=True):
        """Crea (y lanza) un trabajo del agente que vuelve a construir el curso con las habilidades actuales.
        El curso original no se toca hasta que el agente termina con éxito."""
        jobs = self.env["campus.agent.job"].sudo()
        for course in self:
            job = jobs.create({
                "name": course.name, "regenerate_course_id": course.id,
                "certification_id": course.certification_id.id or False,
                "syllabus_file": course.syllabus_file or False, "syllabus_filename": course.syllabus_filename or False,
                "deep_research": deep_research and not economy, "economy": economy, "user_id": self.env.user.id,
                "params": {"name": course.name, "cert_mode": "fixed", "date_start": str(course.date_start or ""),
                           "date_end": str(course.date_end or ""), "modality": course.modality or "virtual",
                           "instructions": (instructions or course.tutor_prompt or "")[:4000],
                           "teacher_ids": course.teacher_ids.ids, "use_ai": True, "regenerate": True},
            })
            course._current_content_materials(job)
            if files:
                job.add_materials(files)
            jobs |= job
        if start and jobs:
            jobs.action_start_sequence()
        return jobs

    @api.model
    def regenerate_all(self, deep_research=False, economy=True):
        courses = self.sudo().search([("state", "!=", "closed"), ("name", "not like", "[Regenerando]%")])
        return courses.action_regenerate(deep_research=deep_research, economy=economy)


def _thread_run_many(dbname, job_ids, uid):
    from odoo.modules.registry import Registry
    import time as _t
    _t.sleep(0.5)
    for jid in job_ids:
        try:
            registry = Registry(dbname)
            with registry.cursor() as cr:
                env = api.Environment(cr, uid, {"lang": "es_CO", "tz": "America/Bogota"})
                env["campus.agent.job"].browse(jid)._run()
        except Exception:  # noqa: BLE001
            _logger.exception("Fallo del agente %s", jid)


class CampusAgentJobSequence(models.Model):
    _inherit = "campus.agent.job"

    def action_start_sequence(self):
        """Ejecuta varios trabajos uno tras otro en un solo hilo (evita superar los límites del proveedor)."""
        self.write({"state": "queued", "progress": 0, "error": False, "heartbeat": fields.Datetime.now()})
        ids = self.ids
        self.env.cr.postcommit.add(lambda: threading.Thread(
            target=_thread_run_many, args=(self.env.cr.dbname, ids, self.env.uid),
            name="campus-agent-seq", daemon=True).start())
        return True


class CampusAgentJobStale(models.Model):
    _inherit = "campus.agent.job"

    def is_stale(self):
        """Un trabajo en cola detrás de otro que sí avanza (regeneración en serie) no está detenido."""
        self.ensure_one()
        if self.state == "queued":
            from datetime import timedelta
            alive = self.search_count([("state", "=", "running"), ("id", "!=", self.id),
                                       ("heartbeat", ">", fields.Datetime.now() - timedelta(minutes=12))])
            if alive:
                return False
        return super().is_stale()


class CampusCourseAutoRegen(models.Model):
    _inherit = "campus.course"

    @api.model
    def regen_status(self):
        """Trabajos de la última regeneración masiva (para el aviso del administrador)."""
        ids = (self.env["ir.config_parameter"].sudo().get_param("campus_pi.regen_jobs") or "").split(",")
        jobs = self.env["campus.agent.job"].sudo().browse([int(x) for x in ids if x.isdigit()]).exists()
        pending = self.env["ir.config_parameter"].sudo().get_param("campus_pi.regen_pending") == "1"
        return {"jobs": jobs, "pending": pending,
                "active": any(j.state in ("queued", "running") and not j.is_stale() for j in jobs)}

    @api.model
    def auto_regenerate_pending(self):
        """Tras actualizar a la versión 17.0.1.7.0 se regeneran una sola vez todos los cursos, cuando un
        administrador entra al campus y ya hay un proveedor de IA configurado."""
        icp = self.env["ir.config_parameter"].sudo()
        if icp.get_param("campus_pi.regen_pending") != "1" or not self.env["campus.ai.agent"].sudo().is_enabled():
            return self.env["campus.agent.job"]
        icp.set_param("campus_pi.regen_pending", False)
        jobs = self.regenerate_all()
        icp.set_param("campus_pi.regen_jobs", ",".join(str(i) for i in jobs.ids))
        return jobs
