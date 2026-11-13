# -*- coding: utf-8 -*-
"""Corrige el nombre InnobaTech -> InnovaTech en datos ya cargados (registros noupdate)."""


def migrate(cr, version):
    cr.execute("""UPDATE res_company SET name = replace(name, 'InnobaTech', 'InnovaTech')
                  WHERE name LIKE '%InnobaTech%'""")
    cr.execute("""UPDATE res_partner SET name = replace(name, 'InnobaTech', 'InnovaTech')
                  WHERE name LIKE '%InnobaTech%'""")
    for table, col in (("campus_course", "description"), ("campus_lesson", "content"),
                       ("campus_lesson", "ai_guide"), ("campus_course", "ai_log")):
        cr.execute("""SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s""",
                   (table, col))
        if cr.fetchone():
            cr.execute("UPDATE %s SET %s = replace(%s::text, 'InnobaTech', 'InnovaTech')::%s "
                       "WHERE %s::text LIKE '%%InnobaTech%%'" % (
                           table, col, col,
                           "jsonb" if _is_jsonb(cr, table, col) else "text", col))


def _is_jsonb(cr, table, col):
    cr.execute("SELECT data_type FROM information_schema.columns WHERE table_name=%s AND column_name=%s",
               (table, col))
    row = cr.fetchone()
    return bool(row and row[0] == "jsonb")
