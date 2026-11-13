# -*- coding: utf-8 -*-
"""Claude Sonnet 4.5 fue reemplazado: se actualiza el modelo guardado por el recomendado."""


def migrate(cr, version):
    for key in ("campus_pi.claude_model", "campus_pi.ai_model"):
        cr.execute("""UPDATE ir_config_parameter SET value = 'claude-sonnet-5-5'
                      WHERE key = %s AND value IN ('claude-sonnet-4-5', 'claude-sonnet-4-5-20250929')""", (key,))
