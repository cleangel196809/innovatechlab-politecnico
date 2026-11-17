# -*- coding: utf-8 -*-
"""Cuentas del campus: cambio obligatorio de la contraseña inicial y recuperación por correo."""
import hashlib
import re
import secrets
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .user_import import WHATSAPP_COURSES

RESET_HOURS = 2


def _hash(token):
    return hashlib.sha256((token or "").encode()).hexdigest()


def check_password_rules(pwd, env=None):
    if len(pwd or "") < 8:
        raise UserError(_("La contraseña debe tener al menos 8 caracteres."))
    if not (re.search(r"[A-Za-z]", pwd) and re.search(r"\d", pwd)):
        raise UserError(_("La contraseña debe combinar letras y números."))
    if env is not None:
        from .user_import import default_password
        if pwd == default_password(env):
            raise UserError(_("La nueva contraseña no puede ser la contraseña por defecto."))


class ResUsersAccount(models.Model):
    _inherit = "res.users"

    campus_must_change_password = fields.Boolean(
        "Debe cambiar la contraseña", help="Se pide al ingresar por primera vez con la contraseña por defecto.")
    campus_reset_hash = fields.Char(groups="base.group_system", copy=False)
    campus_reset_expiry = fields.Datetime(groups="base.group_system", copy=False)

    def campus_issue_reset_token(self):
        """Crea un enlace de un solo uso (válido 2 horas). Devuelve el token en claro (solo para el correo)."""
        self.ensure_one()
        token = secrets.token_urlsafe(32)
        self.sudo().write({"campus_reset_hash": _hash(token),
                           "campus_reset_expiry": fields.Datetime.now() + timedelta(hours=RESET_HOURS)})
        return token

    @api.model
    def campus_user_from_token(self, token):
        if not token or len(token) < 20:
            return self.browse()
        user = self.sudo().search([("campus_reset_hash", "=", _hash(token))], limit=1)
        if not user or not user.campus_reset_expiry or user.campus_reset_expiry < fields.Datetime.now():
            return self.browse()
        return user

    def campus_set_password(self, new_password):
        self.ensure_one()
        check_password_rules(new_password, self.env)
        self.sudo().write({"password": new_password, "campus_must_change_password": False,
                           "campus_reset_hash": False, "campus_reset_expiry": False})

    def campus_reset_to_default(self):
        """Acción del administrador: vuelve a la contraseña por defecto y exige cambiarla."""
        from .user_import import default_password
        for u in self:
            u.sudo().write({"password": default_password(self.env), "campus_must_change_password": True})


class CampusCourseWhatsapp(models.Model):
    _inherit = "campus.course"

    whatsapp_required = fields.Boolean(
        "Pedir WhatsApp a los estudiantes", compute="_compute_whatsapp_required", store=True, readonly=False,
        help="Se marca solo en cursos de inglés o informática. En la carga por Excel se avisa si falta el número.")

    @api.depends("name")
    def _compute_whatsapp_required(self):
        for c in self:
            c.whatsapp_required = bool(WHATSAPP_COURSES.search(c.name or ""))
