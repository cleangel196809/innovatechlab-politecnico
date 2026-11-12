# -*- coding: utf-8 -*-
import os
import secrets

from . import models
from . import controllers
from . import wizard


def post_init_hook(env):
    """Guarda adjuntos en PostgreSQL (Render free no tiene disco persistente)."""
    env["ir.config_parameter"].sudo().set_param("ir_attachment.location", "db")
    env["ir.attachment"].sudo().force_storage()
    # Idioma español (Colombia) para los usuarios demo si está cargado (--load-language=es_CO)
    lang = env["res.lang"].sudo().search([("code", "=", "es_CO"), ("active", "=", True)], limit=1)
    if lang:
        logins = ["administrador.prueba@pi.edu.co", "gustavo.contreras@pi.edu.co", "docente.prueba@pi.edu.co",
                  "prueba.estudiante@pi.edu.co", "prueba.estudiante2@pi.edu.co", "admin"]
        env["res.users"].sudo().search([("login", "in", logins)]).write({"lang": "es_CO"})

    # Seguridad: Odoo crea el usuario "admin" con contraseña "admin". La reemplazamos.
    admin = env.ref("base.user_admin", raise_if_not_found=False)
    if admin:
        admin.sudo().password = os.environ.get("ODOO_ADMIN_PASSWORD") or secrets.token_urlsafe(16)
