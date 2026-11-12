# -*- coding: utf-8 -*-
from odoo import fields, models


class CampusTutoring(models.Model):
    _name = "campus.tutoring"
    _description = "Tutoría agendada (docente o agente IA)"
    _inherit = ["mail.thread"]
    _order = "datetime desc"

    name = fields.Char("Tema", required=True)
    kind = fields.Selection([("virtual", "Tutoría virtual con docente"), ("ia", "Tutoría con agente IA")],
                            required=True, default="virtual", string="Tipo")
    course_id = fields.Many2one("campus.course", required=True, ondelete="cascade")
    student_id = fields.Many2one("res.users", "Estudiante", required=True)
    teacher_id = fields.Many2one("res.users", "Docente")
    datetime = fields.Datetime("Fecha y hora", required=True)
    duration_min = fields.Integer("Duración (min)", default=30)
    meeting_url = fields.Char("Enlace de videollamada")
    notes = fields.Text("Detalle / dudas del estudiante")
    ai_plan = fields.Html("Plan de estudio preparado por el agente")
    state = fields.Selection(
        [("requested", "Solicitada"), ("confirmed", "Confirmada"), ("done", "Realizada"),
         ("cancel", "Cancelada")], default="requested", tracking=True, string="Estado")

    def action_confirm(self):
        self.write({"state": "confirmed"})

    def action_done(self):
        self.write({"state": "done"})

    def action_cancel(self):
        self.write({"state": "cancel"})


class CampusAiMessage(models.Model):
    _name = "campus.ai.message"
    _description = "Mensaje del tutor IA"
    _order = "id"

    user_id = fields.Many2one("res.users", required=True, index=True, ondelete="cascade")
    course_id = fields.Many2one("campus.course", required=True, index=True, ondelete="cascade")
    role = fields.Selection([("user", "Estudiante"), ("assistant", "Tutor IA")], required=True)
    content = fields.Text(required=True)
