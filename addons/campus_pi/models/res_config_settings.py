# -*- coding: utf-8 -*-
from odoo import fields, models

from ..tools.tts import VOICES

PROVIDER_SELECTION = [
    ("", "Automático (el primero con clave)"), ("gemini", "Gemini (Google) – nivel gratuito"),
    ("groq", "Groq (Llama) – nivel gratuito"), ("anthropic", "Claude (Anthropic)"),
    ("openai", "ChatGPT (OpenAI)"), ("compatible", "Otro compatible con OpenAI (OpenRouter, Ollama…)"),
]


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    campus_ai_provider = fields.Selection(PROVIDER_SELECTION, "Proveedor de IA", config_parameter="campus_pi.ai_provider")
    campus_anthropic_api_key = fields.Char("API key de Anthropic", config_parameter="campus_pi.anthropic_api_key")
    campus_gemini_api_key = fields.Char("API key de Gemini", config_parameter="campus_pi.gemini_api_key")
    campus_groq_api_key = fields.Char("API key de Groq", config_parameter="campus_pi.groq_api_key")
    campus_openai_api_key = fields.Char("API key de OpenAI", config_parameter="campus_pi.openai_api_key")
    campus_compatible_api_key = fields.Char("API key (compatible)", config_parameter="campus_pi.compatible_api_key")
    campus_ai_base_url = fields.Char("URL base (compatible)", config_parameter="campus_pi.ai_base_url")
    campus_ai_model = fields.Char("Modelo", config_parameter="campus_pi.ai_model",
                                  help="Vacío = modelo recomendado del proveedor.")
    campus_claude_model = fields.Char("Modelo Claude", config_parameter="campus_pi.claude_model")
    campus_tts_voice = fields.Selection(VOICES, "Voz de la narración", config_parameter="campus_pi.tts_voice",
                                        default="es-CO-GonzaloNeural")
    campus_tts_rate = fields.Char("Velocidad de la voz", config_parameter="campus_pi.tts_rate", default="-4%",
                                  help="Porcentaje respecto a la velocidad normal, por ejemplo -4% o +5%.")
