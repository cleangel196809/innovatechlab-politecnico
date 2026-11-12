# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    campus_anthropic_api_key = fields.Char(
        "API key de Anthropic", config_parameter="campus_pi.anthropic_api_key",
        help="Recomendado: definirla como variable de entorno ANTHROPIC_API_KEY en Render "
             "(tiene prioridad y no queda en la base de datos).")
    campus_claude_model = fields.Char(
        "Modelo Claude", config_parameter="campus_pi.claude_model", default="claude-sonnet-4-5")
