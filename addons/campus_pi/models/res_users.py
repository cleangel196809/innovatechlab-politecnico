# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    campus_role = fields.Selection(
        [("admin", "Administrador"), ("teacher", "Docente"), ("student", "Estudiante"), ("none", "-")],
        compute="_compute_campus_role", string="Rol en el campus")
    campus_enrollment_ids = fields.One2many("campus.enrollment", "user_id", "Cursos inscritos")

    def _compute_campus_role(self):
        for u in self:
            if u.has_group("campus_pi.group_campus_admin"):
                u.campus_role = "admin"
            elif u.has_group("campus_pi.group_campus_teacher"):
                u.campus_role = "teacher"
            elif u.has_group("campus_pi.group_campus_student"):
                u.campus_role = "student"
            else:
                u.campus_role = "none"
