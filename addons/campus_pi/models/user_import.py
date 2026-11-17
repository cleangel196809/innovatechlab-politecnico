# -*- coding: utf-8 -*-
"""Creación masiva de estudiantes y docentes a partir de un listado (Excel o CSV)."""
import re

from odoo import api, models

DEFAULT_PASSWORD = "Poli2026*"
WHATSAPP_COURSES = re.compile(r"(?i)ingl[eé]s|english|inform[aá]tica")


def default_password(env):
    return env["ir.config_parameter"].sudo().get_param("campus_pi.default_password") or DEFAULT_PASSWORD


class CampusUserImport(models.AbstractModel):
    _name = "campus.user.import"
    _description = "Importación masiva de usuarios del campus"

    @api.model
    def import_people(self, people, role="student", course=None, password=None):
        """people: [{name, email, phone, whatsapp}]. role: student|teacher. Las cuentas nuevas reciben la
        contraseña por defecto (Poli2026*) y deben cambiarla en su primer ingreso."""
        password = default_password(self.env)
        need_wa = bool(course and role == "student" and course.whatsapp_required)
        Users = self.env["res.users"].sudo().with_context(no_reset_password=True, active_test=False)
        g_student = self.env.ref("campus_pi.group_campus_student")
        g_teacher = self.env.ref("campus_pi.group_campus_teacher")
        g_portal = self.env.ref("base.group_portal")
        role_label = "Docente" if role == "teacher" else "Estudiante"
        out = []
        for p in people:
            res = {"name": p["name"], "email": p["email"], "phone": p.get("phone") or "", "role": role_label,
                   "whatsapp": p.get("whatsapp") or "", "password": "", "ok": True}
            try:
                with self.env.cr.savepoint():
                    user = Users.search(["|", ("login", "=ilike", p["email"]), ("email", "=ilike", p["email"])], limit=1)
                    notes = []
                    if user:
                        if not user.active:
                            user.active = True
                            notes.append("reactivado")
                        if role == "teacher" and not user.has_group("campus_pi.group_campus_teacher"):
                            user.write({"groups_id": [(3, g_student.id), (3, g_portal.id), (4, g_teacher.id)]})
                            notes.append("ahora es docente")
                        elif role == "student" and not user.has_group("base.group_user") \
                                and not user.has_group("campus_pi.group_campus_student"):
                            user.write({"groups_id": [(4, g_student.id)]})
                            notes.append("ahora es estudiante")
                        elif role == "student" and user.has_group("base.group_user"):
                            notes.append("ya es usuario interno (docente/administrador)")
                        self._contact(user, res)
                        status = "Ya existía" + (" (%s)" % ", ".join(notes) if notes else "")
                    else:
                        user = Users.create({
                            "name": p["name"], "login": p["email"], "email": p["email"], "password": password,
                            "tz": "America/Bogota", "lang": self._lang(), "campus_must_change_password": True,
                            "groups_id": [(6, 0, [(g_teacher if role == "teacher" else g_student).id])],
                        })
                        self._contact(user, res)
                        res["password"] = password
                        status = "Creado"
                    if course:
                        if role == "teacher":
                            if user not in course.teacher_ids:
                                course.sudo().write({"teacher_ids": [(4, user.id)]})
                                status += " · asignado al curso"
                        elif user not in course.enrollment_ids.mapped("user_id"):
                            course.sudo().enroll_users(user)
                            status += " · inscrito en el curso"
                    if need_wa and not res["whatsapp"]:
                        status += " · ⚠️ falta el WhatsApp (se requiere en cursos de inglés o informática)"
                    res["status"] = status
            except Exception as e:  # noqa: BLE001
                res.update({"ok": False, "status": "Error: %s" % str(e)[:160]})
            out.append(res)
        return out

    @api.model
    def _contact(self, user, res):
        vals = {}
        if res.get("phone") and not user.partner_id.phone:
            vals["phone"] = res["phone"]
        if res.get("whatsapp") and not user.partner_id.mobile:
            vals["mobile"] = res["whatsapp"]
        if vals:
            user.partner_id.write(vals)

    @api.model
    def _lang(self):
        langs = self.env["res.lang"].sudo().search([("active", "=", True)]).mapped("code")
        return "es_CO" if "es_CO" in langs else ("es_419" if "es_419" in langs else self.env.lang or "en_US")
