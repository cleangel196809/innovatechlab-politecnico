# -*- coding: utf-8 -*-
import random

from odoo import api, fields, models


class CampusQuestion(models.Model):
    _name = "campus.question"
    _description = "Pregunta del simulador de certificación"
    _order = "course_id, domain, id"

    course_id = fields.Many2one("campus.course", required=True, ondelete="cascade", index=True)
    domain = fields.Char("Dominio de la certificación", default="General")
    name = fields.Text("Enunciado", required=True)
    explanation = fields.Text("Explicación (retroalimentación)")
    difficulty = fields.Selection([("1", "Baja"), ("2", "Media"), ("3", "Alta")], default="2")
    source = fields.Selection(
        [("manual", "Manual"), ("gift", "Importada GIFT"), ("ai", "Generada por agente IA")],
        default="manual", string="Origen")
    option_ids = fields.One2many("campus.question.option", "question_id", "Opciones")
    active = fields.Boolean(default=True)


class CampusQuestionOption(models.Model):
    _name = "campus.question.option"
    _description = "Opción de respuesta"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    question_id = fields.Many2one("campus.question", required=True, ondelete="cascade")
    name = fields.Text("Opción", required=True)
    is_correct = fields.Boolean("Correcta")
    feedback = fields.Text("Retroalimentación")


class CampusSimAttempt(models.Model):
    _name = "campus.sim.attempt"
    _description = "Intento en el simulador de certificación"
    _order = "create_date desc"

    enrollment_id = fields.Many2one("campus.enrollment", required=True, ondelete="cascade", index=True)
    user_id = fields.Many2one(related="enrollment_id.user_id", store=True)
    course_id = fields.Many2one(related="enrollment_id.course_id", store=True)
    date_start = fields.Datetime(default=fields.Datetime.now)
    date_end = fields.Datetime()
    deadline = fields.Datetime()
    state = fields.Selection([("open", "En curso"), ("done", "Finalizado")], default="open")
    answer_ids = fields.One2many("campus.sim.answer", "attempt_id")
    score = fields.Float("Puntaje (%)")
    passed = fields.Boolean("Aprobado")
    domain_report = fields.Json("Resultado por dominio")

    @api.model
    def start(self, enrollment):
        course = enrollment.course_id
        cert = course.certification_id
        n = cert.num_questions if cert else 20
        minutes = cert.duration_min if cert else 45
        questions = course.question_ids.filtered("active")
        picked = random.sample(list(questions), min(n, len(questions)))
        attempt = self.sudo().create({
            "enrollment_id": enrollment.id,
            "deadline": fields.Datetime.add(fields.Datetime.now(), minutes=minutes),
            "answer_ids": [(0, 0, {"question_id": q.id, "sequence": i}) for i, q in enumerate(picked)],
        })
        return attempt

    def finish(self, answers):
        """answers: {answer_id: option_id}"""
        self.ensure_one()
        for ans in self.answer_ids:
            opt_id = answers.get(ans.id)
            ans.option_id = opt_id and int(opt_id) or False
        report = {}
        for ans in self.answer_ids:
            d = ans.question_id.domain or "General"
            r = report.setdefault(d, {"ok": 0, "total": 0})
            r["total"] += 1
            r["ok"] += 1 if ans.is_correct else 0
        for d, r in report.items():
            r["pct"] = round(100.0 * r["ok"] / r["total"], 1) if r["total"] else 0
        total = len(self.answer_ids)
        ok = len(self.answer_ids.filtered("is_correct"))
        score = round(100.0 * ok / total, 1) if total else 0.0
        cert = self.course_id.certification_id
        passing = cert.passing_score if cert else 70.0
        self.write({
            "state": "done", "date_end": fields.Datetime.now(), "score": score,
            "passed": score >= passing, "domain_report": report,
        })
        self.enrollment_id.check_badge()
        return self


class CampusSimAnswer(models.Model):
    _name = "campus.sim.answer"
    _description = "Respuesta en simulador"
    _order = "sequence, id"

    sequence = fields.Integer()
    attempt_id = fields.Many2one("campus.sim.attempt", required=True, ondelete="cascade")
    question_id = fields.Many2one("campus.question", required=True, ondelete="cascade")
    option_id = fields.Many2one("campus.question.option")
    is_correct = fields.Boolean(compute="_compute_correct", store=True)

    @api.depends("option_id")
    def _compute_correct(self):
        for a in self:
            a.is_correct = bool(a.option_id and a.option_id.is_correct)
