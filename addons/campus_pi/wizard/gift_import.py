# -*- coding: utf-8 -*-
import base64

from odoo import fields, models, _
from odoo.exceptions import UserError

from ..tools.gift import parse_gift


class CampusGiftImport(models.TransientModel):
    _name = "campus.gift.import"
    _description = "Importar preguntas GIFT (Moodle)"

    course_id = fields.Many2one("campus.course", required=True)
    domain = fields.Char("Dominio a asignar", default="General")
    file = fields.Binary("Archivo .txt GIFT", required=True)
    filename = fields.Char()

    def action_import(self):
        self.ensure_one()
        text = base64.b64decode(self.file).decode("utf-8-sig", errors="ignore")
        items = parse_gift(text)
        if not items:
            raise UserError(_("No se encontraron preguntas de opción múltiple en el archivo."))
        for q in items:
            q["domain"] = self.domain
        self.env["campus.ai.agent"]._create_questions(self.course_id, items, source="gift")
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"title": _("Importación GIFT"), "type": "success",
                       "message": _("%s preguntas importadas.") % len(items),
                       "next": {"type": "ir.actions.act_window_close"}},
        }
