# -*- coding: utf-8 -*-
"""Marca los cursos existentes para regenerarlos una vez con los agentes nuevos (formato institucional,
voz natural, actividad H5P, caso con rúbrica). La regeneración arranca cuando un administrador entra al
campus y hay un proveedor de IA configurado (ver campus.course.auto_regenerate_pending)."""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        INSERT INTO ir_config_parameter (key, value, create_uid, write_uid, create_date, write_date)
        VALUES ('campus_pi.regen_pending', '1', 1, 1, now() at time zone 'UTC', now() at time zone 'UTC')
        ON CONFLICT (key) DO UPDATE SET value = '1'
    """)
    _logger.info("campus_pi: cursos marcados para regenerarse con los agentes nuevos")
