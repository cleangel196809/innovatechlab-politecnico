# -*- coding: utf-8 -*-
"""Recuperación de contraseña por correo y cambio obligatorio de la contraseña inicial."""
import logging

from markupsafe import escape

from odoo import http, _
from odoo.exceptions import AccessDenied, UserError
from odoo.http import request

from .main import _uid_is_public
from ..tools import mailer

_logger = logging.getLogger(__name__)


def _account(values):
    base = {"error": None, "info": None, "sent": False, "done": False, "token": None, "account": None, "action": ""}
    base.update(values)
    return request.render("campus_pi.campus_account", base)


class CampusAccount(http.Controller):

    @http.route("/campus/recuperar", type="http", auth="public", methods=["GET", "POST"], sitemap=False)
    def recover(self, email=None, **kw):
        values = {"mode": "recover"}
        if request.httprequest.method == "POST":
            email = (email or "").strip().lower()
            user = request.env["res.users"].sudo().search(
                ["|", ("login", "=ilike", email), ("email", "=ilike", email), ("share", "in", (True, False))], limit=1)
            if user and user.active:
                token = user.campus_issue_reset_token()
                link = "%s/campus/restablecer?token=%s" % (request.httprequest.host_url.rstrip("/"), token)
                html = (
                    "<div style='font-family:Arial,sans-serif;max-width:560px'>"
                    "<h2 style='color:#0B1F5B'>InnovaTech Lab · Politécnico Internacional</h2>"
                    "<p>Hola, %s:</p><p>Recibimos una solicitud para restablecer la contraseña de tu cuenta <b>%s</b>.</p>"
                    "<p><a href='%s' style='background:#1E9BD7;color:#fff;padding:10px 18px;border-radius:8px;"
                    "text-decoration:none'>Crear una contraseña nueva</a></p>"
                    "<p style='color:#595959;font-size:13px'>El enlace vence en 2 horas y solo sirve una vez. Si no fuiste tú, "
                    "ignora este correo: tu contraseña no cambia.</p></div>") % (
                    escape(user.name), escape(user.login), escape(link))
                ok, detail = mailer.send(request.env, user.email or user.login, "Restablece tu contraseña · InnovaTech Lab", html)
                if not ok:
                    _logger.warning("Recuperación de contraseña sin enviar (%s): %s", user.login, detail)
            # Respuesta idéntica exista o no la cuenta (no revela qué correos están registrados)
            values.update({"sent": True, "info": _(
                "Si el correo está registrado, te enviamos un enlace para crear una contraseña nueva. Revisa también "
                "la carpeta de spam. Si no llega en unos minutos, pide al administrador que restablezca tu acceso.")})
        return _account(values)

    @http.route("/campus/restablecer", type="http", auth="public", methods=["GET", "POST"], sitemap=False)
    def reset(self, token=None, new_password=None, confirm_password=None, **kw):
        user = request.env["res.users"].sudo().campus_user_from_token(token)
        values = {"mode": "reset", "token": token, "action": "/campus/restablecer", "account": user.login if user else None}
        if not user:
            values.update({"error": _("El enlace no es válido o ya venció. Solicita uno nuevo."), "done": True})
            return _account(values)
        if request.httprequest.method == "POST":
            try:
                if new_password != confirm_password:
                    raise UserError(_("Las contraseñas no coinciden."))
                user.campus_set_password(new_password)
                return request.redirect("/campus/login?info=clave")
            except UserError as e:
                values["error"] = e.args[0]
        return _account(values)

    @http.route("/campus/cambiar-clave", type="http", auth="user", methods=["GET", "POST"], sitemap=False)
    def change(self, old_password=None, new_password=None, confirm_password=None, **kw):
        user = request.env.user
        values = {"mode": "change", "action": "/campus/cambiar-clave", "account": user.login}
        if request.httprequest.method == "POST":
            try:
                if new_password != confirm_password:
                    raise UserError(_("Las contraseñas no coinciden."))
                from ..models.account import check_password_rules
                check_password_rules(new_password, request.env)
                try:
                    user._check_credentials(old_password, {"interactive": True})
                except AccessDenied:
                    raise UserError(_("La contraseña actual no es correcta."))
                login = user.login
                user.campus_set_password(new_password)
                request.env.cr.commit()
                request.session.authenticate(request.db, login, new_password)  # el cambio cierra la sesión anterior
                return request.redirect("/campus")
            except UserError as e:
                values["error"] = e.args[0]
        return _account(values)
