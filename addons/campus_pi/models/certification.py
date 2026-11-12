# -*- coding: utf-8 -*-
from odoo import fields, models


class CampusCertification(models.Model):
    _name = "campus.certification"
    _description = "Certificación internacional objetivo"
    _order = "provider, name"

    name = fields.Char("Certificación", required=True)
    provider = fields.Char("Entidad certificadora", required=True)
    exam_code = fields.Char("Código de examen")
    url = fields.Char("Página oficial")
    level = fields.Selection(
        [("fundamental", "Fundamentos"), ("associate", "Asociado"), ("professional", "Profesional")],
        default="fundamental", string="Nivel")
    passing_score = fields.Float("Puntaje mínimo (%)", default=70.0)
    num_questions = fields.Integer("Preguntas del simulador", default=20)
    duration_min = fields.Integer("Duración del simulador (min)", default=45)
    price_note = fields.Char("Costo / modalidad")
    description = fields.Html("Descripción")
    verify_note = fields.Char(
        "Nota de verificación",
        help="Recordatorio de revisar en la página oficial antes de cada cohorte: "
             "los proveedores cambian códigos, precios y temarios.")
    domain_ids = fields.One2many("campus.cert.domain", "certification_id", "Dominios evaluados")
    course_ids = fields.One2many("campus.course", "certification_id", "Cursos")
    color = fields.Char("Color", default="#160B8B")


class CampusCertDomain(models.Model):
    _name = "campus.cert.domain"
    _description = "Dominio / área evaluada en la certificación"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    certification_id = fields.Many2one("campus.certification", required=True, ondelete="cascade")
    name = fields.Char("Dominio", required=True)
    weight = fields.Float("Peso (%)")
