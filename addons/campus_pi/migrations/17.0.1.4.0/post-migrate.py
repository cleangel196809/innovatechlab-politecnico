# -*- coding: utf-8 -*-
"""Elimina opciones de respuesta duplicadas.

El arranque en Render pasaba ``-i campus_pi`` en cada inicio; Odoo recargaba los datos
iniciales en modo "init" y agregaba otra copia de las opciones de cada pregunta.
Se conserva la opción más antigua de cada grupo (pregunta + texto) y las respuestas de
los intentos del simulador se reasignan a ella.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        WITH g AS (
            SELECT id, MIN(id) OVER (PARTITION BY question_id, btrim(name)) AS keep_id
              FROM campus_question_option
        )
        SELECT id, keep_id FROM g WHERE id <> keep_id
    """)
    pairs = cr.fetchall()
    if not pairs:
        return
    cr.execute("CREATE TEMP TABLE _cp_dup (id int PRIMARY KEY, keep_id int) ON COMMIT DROP")
    cr.executemany("INSERT INTO _cp_dup VALUES (%s, %s)", pairs)
    cr.execute("""
        UPDATE campus_sim_answer a SET option_id = d.keep_id
          FROM _cp_dup d WHERE a.option_id = d.id
    """)
    # Si alguna copia era la correcta, la opción conservada también debe serlo
    cr.execute("""
        UPDATE campus_question_option o SET is_correct = TRUE
          FROM _cp_dup d JOIN campus_question_option c ON c.id = d.id
         WHERE o.id = d.keep_id AND c.is_correct AND NOT COALESCE(o.is_correct, FALSE)
    """)
    cr.execute("DELETE FROM campus_question_option WHERE id IN (SELECT id FROM _cp_dup)")
    _logger.info("campus_pi: %s opciones duplicadas eliminadas", len(pairs))
