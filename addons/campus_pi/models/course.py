# -*- coding: utf-8 -*-
import base64
import uuid

from odoo import api, fields, models
from odoo.tools import file_open

LESSON_TYPES = [
    ("lectura", "Lectura"),
    ("video", "Video"),
    ("presentacion", "Presentación interactiva"),
    ("infografia", "Infografía"),
    ("actividad", "Actividad formativa"),
    ("caso", "Caso integrador"),
    ("quiz", "Cuestionario"),
    ("sesion_virtual", "Sesión sincrónica virtual"),
    ("sesion_presencial", "Sesión presencial asistida por IA"),
    ("laboratorio", "Laboratorio práctico"),
]


class CampusCourse(models.Model):
    _name = "campus.course"
    _description = "Curso / microcertificación"
    _inherit = ["mail.thread"]
    _order = "date_start desc, name"

    name = fields.Char("Curso", required=True, tracking=True)
    code = fields.Char("Código")
    subtitle = fields.Char("Subtítulo")
    image = fields.Binary("Imagen", attachment=True)
    color = fields.Char("Color de tarjeta", default="#160B8B")
    icon = fields.Char("Ícono (emoji)", default="🎓")
    description = fields.Html("Descripción")
    outcomes = fields.Html("Resultados de aprendizaje")
    skills = fields.Char("Habilidades (separadas por coma)")
    modality = fields.Selection(
        [("virtual", "Virtual"), ("presencial", "Presencial asistida por IA"), ("hibrida", "Híbrida")],
        default="virtual", string="Modalidad", required=True)
    hours = fields.Integer("Horas totales", default=144)
    level = fields.Selection(
        [("basico", "Básico"), ("intermedio", "Intermedio"), ("avanzado", "Avanzado")],
        default="intermedio", string="Nivel")
    date_start = fields.Date("Inicio")
    date_end = fields.Date("Fin")
    state = fields.Selection(
        [("draft", "Borrador"), ("published", "Publicado"), ("closed", "Cerrado")],
        default="draft", tracking=True, string="Estado")
    certification_id = fields.Many2one("campus.certification", "Certificación internacional objetivo")
    teacher_ids = fields.Many2many("res.users", "campus_course_teacher_rel", "course_id", "user_id",
                                   "Docentes")
    section_ids = fields.One2many("campus.section", "course_id", "Núcleos / secciones")
    lesson_ids = fields.One2many("campus.lesson", "course_id", "Lecciones")
    enrollment_ids = fields.One2many("campus.enrollment", "course_id", "Inscripciones")
    question_ids = fields.One2many("campus.question", "course_id", "Banco de preguntas")
    student_count = fields.Integer(compute="_compute_counts", string="Estudiantes")
    lesson_count = fields.Integer(compute="_compute_counts", string="N.º lecciones")
    question_count = fields.Integer(compute="_compute_counts", string="N.º preguntas")
    syllabus_file = fields.Binary("Syllabus", attachment=True)
    syllabus_filename = fields.Char("Archivo syllabus")
    syllabus_text = fields.Text("Texto del syllabus (contexto del agente)")
    ai_generated = fields.Boolean("Generado por agente IA")
    ai_log = fields.Text("Bitácora del agente")
    tutor_prompt = fields.Text(
        "Instrucciones del tutor IA",
        help="Personaliza el comportamiento del tutor IA en este curso.")
    reference_model = fields.Char(
        "Modelo de referencia",
        help="Ej.: IBM AI Engineering (Coursera). Sirve como referente de estructura.")

    @api.depends("enrollment_ids", "lesson_ids", "question_ids")
    def _compute_counts(self):
        for c in self:
            c.student_count = len(c.enrollment_ids)
            c.lesson_count = len(c.lesson_ids)
            c.question_count = len(c.question_ids)

    def action_publish(self):
        self.write({"state": "published"})

    def action_close(self):
        self.write({"state": "closed"})

    def action_open_campus(self):
        self.ensure_one()
        return {"type": "ir.actions.act_url", "url": "/campus/curso/%s" % self.id, "target": "new"}

    def action_ai_generate_questions(self):
        for course in self:
            self.env["campus.ai.agent"].generate_questions(course, 10)
        return True

    def enroll_users(self, users):
        Enrollment = self.env["campus.enrollment"].sudo()
        for course in self:
            existing = course.enrollment_ids.mapped("user_id")
            for u in users - existing:
                Enrollment.create({"course_id": course.id, "user_id": u.id})


class CampusSection(models.Model):
    _name = "campus.section"
    _description = "Núcleo / sección del curso"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    course_id = fields.Many2one("campus.course", required=True, ondelete="cascade")
    name = fields.Char("Sección", required=True)
    objective = fields.Text("Objetivo de aprendizaje")
    date_start = fields.Date("Desde")
    date_end = fields.Date("Hasta")
    lesson_ids = fields.One2many("campus.lesson", "section_id", "Lecciones")


class CampusLesson(models.Model):
    _name = "campus.lesson"
    _description = "Lección / actividad"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    section_id = fields.Many2one("campus.section", required=True, ondelete="cascade")
    course_id = fields.Many2one(related="section_id.course_id", store=True, index=True)
    name = fields.Char("Lección", required=True)
    lesson_type = fields.Selection(LESSON_TYPES, default="lectura", required=True, string="Tipo")
    summary = fields.Char("Resumen")
    content = fields.Html("Contenido", sanitize_attributes=False)
    video_url = fields.Char("URL de video (embed)")
    resource_url = fields.Char("Recurso externo")
    attachment = fields.Binary("Archivo", attachment=True)
    attachment_name = fields.Char("Nombre del archivo")
    duration_min = fields.Integer("Duración (min)", default=30)
    session_datetime = fields.Datetime("Fecha de la sesión")
    meeting_url = fields.Char("Enlace de la sesión (Meet/Teams)")
    location = fields.Char("Lugar (presencial)")
    ai_guide = fields.Html("Guion del agente IA",
                           help="Para sesiones presenciales/virtuales asistidas por IA: "
                                "agenda, preguntas detonantes y retos que el agente propone.")


class CampusEnrollment(models.Model):
    _name = "campus.enrollment"
    _description = "Inscripción de estudiante"
    _order = "create_date desc"
    _rec_name = "user_id"

    course_id = fields.Many2one("campus.course", required=True, ondelete="cascade", index=True)
    user_id = fields.Many2one("res.users", "Estudiante", required=True, ondelete="cascade", index=True)
    date = fields.Date(default=fields.Date.context_today)
    state = fields.Selection(
        [("active", "Activo"), ("completed", "Completado"), ("certified", "Microcredencial emitida")],
        default="active", string="Estado")
    progress_ids = fields.One2many("campus.lesson.progress", "enrollment_id")
    progress = fields.Float("Avance (%)", compute="_compute_progress", store=True)
    best_score = fields.Float("Mejor simulación (%)", compute="_compute_best", store=True)
    attempt_ids = fields.One2many("campus.sim.attempt", "enrollment_id")
    badge_id = fields.Many2one("campus.badge", "Microcredencial")

    _sql_constraints = [("uniq_enroll", "unique(course_id, user_id)", "El estudiante ya está inscrito.")]

    @api.depends("progress_ids.done", "course_id.lesson_ids")
    def _compute_progress(self):
        for e in self:
            total = len(e.course_id.lesson_ids)
            done = len(e.progress_ids.filtered("done"))
            e.progress = round(100.0 * done / total, 1) if total else 0.0

    @api.depends("attempt_ids.score")
    def _compute_best(self):
        for e in self:
            e.best_score = max(e.attempt_ids.mapped("score") or [0.0])

    def check_badge(self):
        """Emite la microcredencial si cumple: 100% lecciones + simulador aprobado."""
        for e in self:
            cert = e.course_id.certification_id
            passing = cert.passing_score if cert else 70.0
            if not e.badge_id and e.progress >= 100 and e.best_score >= passing:
                badge = self.env["campus.badge"].sudo().create({
                    "enrollment_id": e.id,
                    "score": e.best_score,
                })
                e.sudo().write({"badge_id": badge.id, "state": "certified"})


class CampusLessonProgress(models.Model):
    _name = "campus.lesson.progress"
    _description = "Avance por lección"

    enrollment_id = fields.Many2one("campus.enrollment", required=True, ondelete="cascade", index=True)
    lesson_id = fields.Many2one("campus.lesson", required=True, ondelete="cascade")
    done = fields.Boolean(default=True)
    date = fields.Datetime(default=fields.Datetime.now)

    _sql_constraints = [("uniq_prog", "unique(enrollment_id, lesson_id)", "Ya registrado")]


class CampusBadge(models.Model):
    _name = "campus.badge"
    _description = "Microcredencial verificable"
    _rec_name = "code"

    code = fields.Char("Código de verificación", default=lambda s: uuid.uuid4().hex[:12].upper(),
                       readonly=True, index=True, copy=False)
    enrollment_id = fields.Many2one("campus.enrollment", required=True, ondelete="cascade")
    user_id = fields.Many2one(related="enrollment_id.user_id", store=True)
    course_id = fields.Many2one(related="enrollment_id.course_id", store=True)
    certification_id = fields.Many2one(related="course_id.certification_id", store=True)
    date = fields.Date(default=fields.Date.context_today)
    score = fields.Float("Puntaje simulador (%)")

    _sql_constraints = [("uniq_code", "unique(code)", "Código duplicado")]

    def logo_data_uri(self, name="isologo_pi.png"):
        with file_open("campus_pi/static/src/img/%s" % name, "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode()
