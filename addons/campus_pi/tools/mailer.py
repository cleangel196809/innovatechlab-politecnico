# -*- coding: utf-8 -*-
"""Envío de correos del campus (recuperación de contraseña, avisos).

Render gratuito bloquea el SMTP saliente, así que primero se usa una API HTTPS gratuita:
* Brevo   (300 correos/día gratis; basta verificar el correo remitente): clave en Brevo → SMTP y API → Claves API.
* Resend  (3.000/mes gratis; requiere dominio verificado para escribir a cualquier destinatario).
Si no hay clave, se usa el servidor de correo saliente de Odoo (Ajustes → Técnico → Servidores de correo).
Configuración: «Proveedor de IA → Correo saliente» o variables de entorno BREVO_API_KEY / RESEND_API_KEY / MAIL_FROM.
"""
import logging
import os

import requests

_logger = logging.getLogger(__name__)


def settings(env):
    icp = env["ir.config_parameter"].sudo()
    key = icp.get_param("campus_pi.mail_api_key") or os.environ.get("BREVO_API_KEY") or os.environ.get("RESEND_API_KEY") or ""
    prov = icp.get_param("campus_pi.mail_provider") or ""
    if not prov:
        prov = "resend" if (key.startswith("re_") or (not icp.get_param("campus_pi.mail_api_key")
                                                       and os.environ.get("RESEND_API_KEY"))) else ("brevo" if key else "odoo")
    return {"provider": prov, "key": key,
            "from": icp.get_param("campus_pi.mail_from") or os.environ.get("MAIL_FROM") or "",
            "name": icp.get_param("campus_pi.mail_from_name") or "InnovaTech Lab · Politécnico Internacional"}


def send(env, to, subject, html):
    """Envía un correo. Devuelve (True, detalle) o (False, motivo). Nunca lanza excepción."""
    conf = settings(env)
    try:
        if conf["provider"] == "brevo" and conf["key"]:
            if not conf["from"]:
                return False, "Falta el correo remitente (verificado en Brevo)."
            r = requests.post("https://api.brevo.com/v3/smtp/email", timeout=20, headers={
                "api-key": conf["key"], "accept": "application/json", "content-type": "application/json"}, json={
                "sender": {"name": conf["name"], "email": conf["from"]}, "to": [{"email": to}],
                "subject": subject, "htmlContent": html})
            return (r.status_code < 300), ("Brevo %s" % r.status_code if r.status_code < 300 else "Brevo: %s" % r.text[:200])
        if conf["provider"] == "resend" and conf["key"]:
            r = requests.post("https://api.resend.com/emails", timeout=20, headers={
                "Authorization": "Bearer %s" % conf["key"]}, json={
                "from": "%s <%s>" % (conf["name"], conf["from"] or "onboarding@resend.dev"), "to": [to],
                "subject": subject, "html": html})
            return (r.status_code < 300), ("Resend %s" % r.status_code if r.status_code < 300 else "Resend: %s" % r.text[:200])
        if not env["ir.mail_server"].sudo().search_count([]):
            return False, "No hay un servicio de correo configurado (Brevo, Resend o servidor SMTP de Odoo)."
        mail = env["mail.mail"].sudo().create({
            "subject": subject, "body_html": html, "email_to": to, "auto_delete": True,
            "email_from": "%s <%s>" % (conf["name"], conf["from"]) if conf["from"] else False})
        mail.send(raise_exception=True)
        return True, "SMTP de Odoo"
    except Exception as e:  # noqa: BLE001
        _logger.warning("No se pudo enviar el correo a %s: %s", to, e)
        return False, str(e)[:200]
