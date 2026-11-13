# -*- coding: utf-8 -*-
import base64
import logging
import os
import re
from datetime import datetime, timedelta

import pytz
from werkzeug.exceptions import NotFound

from odoo import fields, http, _
from odoo.addons.web.controllers.home import Home
from odoo.exceptions import AccessDenied, UserError
from odoo.http import request

_logger = logging.getLogger(__name__)
MAX_UPLOAD_MB = 40  # Neon gratis tiene 0,5 GB: los videos largos deben ir por enlace (YouTube/Drive)


def _uid_is_public():
    return not request.session.uid or request.env.user._is_public()


class CampusHome(Home):
    """La raíz del sitio y el post-login llevan al campus."""

    @http.route("/", type="http", auth="none")
    def index(self, s_action=None, db=None, **kw):
        return request.redirect("/campus")

    def _login_redirect(self, uid, redirect=None):
        if not redirect:
            return "/campus"
        return super()._login_redirect(uid, redirect=redirect)


class Campus(http.Controller):

    # ------------------------------------------------------------ helpers
    def _env_user(self):
        return request.env.user

    def _role(self):
        return request.env.user.campus_role

    def _render(self, template, values=None):
        vals = {"user": request.env.user, "role": self._role(),
                "ai_enabled": request.env["campus.ai.agent"].sudo().is_enabled(),
                "ai_provider": request.env["campus.ai.agent"].sudo().provider_label(),
                "now": fields.Datetime.now()}
        vals.update(values or {})
        return request.render(template, vals)

    def _course(self, course_id):
        """Devuelve el curso (sudo) si el usuario tiene acceso; si no, 404."""
        user = request.env.user
        course = request.env["campus.course"].sudo().browse(int(course_id)).exists()
        if not course:
            raise NotFound()
        role = user.campus_role
        if role == "admin" or (role == "teacher" and user in course.teacher_ids):
            return course, None
        enrollment = course.enrollment_ids.filtered(lambda e: e.user_id == user)[:1]
        if enrollment and course.state != "draft":
            return course, enrollment
        raise NotFound()

    def _to_utc(self, local_str):
        """'2026-11-20T19:00' en la zona del usuario -> datetime UTC ingenuo."""
        tz = pytz.timezone(request.env.user.tz or "America/Bogota")
        dt = datetime.strptime(local_str, "%Y-%m-%dT%H:%M")
        return tz.localize(dt).astimezone(pytz.utc).replace(tzinfo=None)

    def _require(self, *roles):
        if _uid_is_public():
            return request.redirect("/campus/login")
        if self._role() not in roles:
            raise NotFound()
        return None

    # -------------------------------------------------------------- login
    @http.route("/campus/login", type="http", auth="none", methods=["GET", "POST"], csrf=True, sitemap=False)
    def campus_login(self, login=None, password=None, **kw):
        values = {"error": None, "login": login or ""}
        if request.httprequest.method == "POST":
            try:
                request.session.authenticate(request.db, login, password)
                return request.redirect("/campus")
            except AccessDenied:
                values["error"] = _("Usuario o contraseña incorrectos.")
            except Exception as e:  # noqa: BLE001
                _logger.exception("Login error")
                values["error"] = str(e)
        return request.render("campus_pi.campus_login", values)

    @http.route("/campus/salir", type="http", auth="public", sitemap=False)
    def campus_logout(self, **kw):
        request.session.logout(keep_db=True)
        return request.redirect("/campus/login")

    # ---------------------------------------------------------- dashboard
    @http.route("/campus", type="http", auth="public", sitemap=False)
    def dashboard(self, **kw):
        if _uid_is_public():
            return request.redirect("/campus/login")
        user = request.env.user
        role = self._role()
        Course = request.env["campus.course"].sudo()
        if role == "admin":
            env = request.env
            stats = {
                "courses": Course.search_count([]),
                "students": env["res.users"].sudo().search_count([("groups_id", "in", env.ref("campus_pi.group_campus_student").id)]),
                "enrollments": env["campus.enrollment"].sudo().search_count([]),
                "badges": env["campus.badge"].sudo().search_count([]),
                "attempts": env["campus.sim.attempt"].sudo().search_count([("state", "=", "done")]),
                "ai_msgs": env["campus.ai.message"].sudo().search_count([("role", "=", "assistant")]),
                "tutorings": env["campus.tutoring"].sudo().search_count([("state", "in", ("requested", "confirmed"))]),
            }
            return self._render("campus_pi.dashboard_admin", {"stats": stats, "courses": Course.search([])})
        if role == "teacher":
            courses = Course.search([("teacher_ids", "in", user.id)])
            now = fields.Datetime.now()
            sessions = request.env["campus.lesson"].sudo().search([
                ("course_id", "in", courses.ids), ("session_datetime", ">=", now - timedelta(hours=3)),
                ("session_datetime", "<=", now + timedelta(days=21))], order="session_datetime")
            tutorings = request.env["campus.tutoring"].sudo().search([
                ("course_id", "in", courses.ids), ("kind", "=", "virtual"),
                ("state", "in", ("requested", "confirmed"))], order="datetime")
            return self._render("campus_pi.dashboard_teacher",
                                {"courses": courses, "sessions": sessions, "tutorings": tutorings})
        if role == "student":
            enrollments = request.env["campus.enrollment"].sudo().search(
                [("user_id", "=", user.id), ("course_id.state", "!=", "draft")])
            return self._render("campus_pi.dashboard_student", {"enrollments": enrollments})
        return self._render("campus_pi.no_role")

    # ------------------------------------------------------------ cursos
    @http.route("/campus/curso/<int:course_id>", type="http", auth="user", sitemap=False)
    def course_home(self, course_id, **kw):
        course, enrollment = self._course(course_id)
        done = set(enrollment.progress_ids.mapped("lesson_id").ids) if enrollment else set()
        return self._render("campus_pi.course_lessons", {
            "course": course, "enrollment": enrollment, "done": done, "tab": "lessons", "lesson": None})

    @http.route("/campus/curso/<int:course_id>/leccion/<int:lesson_id>", type="http", auth="user", sitemap=False)
    def lesson(self, course_id, lesson_id, **kw):
        course, enrollment = self._course(course_id)
        lesson = course.lesson_ids.filtered(lambda l: l.id == lesson_id)
        if not lesson:
            raise NotFound()
        lessons = course.lesson_ids.sorted(lambda l: (l.section_id.sequence, l.sequence, l.id))
        idx = list(lessons.ids).index(lesson.id)
        done = set(enrollment.progress_ids.mapped("lesson_id").ids) if enrollment else set()
        return self._render("campus_pi.course_lessons", {
            "course": course, "enrollment": enrollment, "done": done, "tab": "lessons", "lesson": lesson,
            "can_edit": self._can_edit_course(course), "max_mb": MAX_UPLOAD_MB,
            "prev": lessons[idx - 1] if idx > 0 else None,
            "next": lessons[idx + 1] if idx + 1 < len(lessons) else None})

    @http.route("/campus/curso/<int:course_id>/leccion/<int:lesson_id>/completar", type="http",
                auth="user", methods=["POST"], sitemap=False)
    def lesson_done(self, course_id, lesson_id, **kw):
        course, enrollment = self._course(course_id)
        if enrollment and lesson_id in course.lesson_ids.ids and lesson_id not in enrollment.progress_ids.mapped("lesson_id").ids:
            request.env["campus.lesson.progress"].sudo().create(
                {"enrollment_id": enrollment.id, "lesson_id": lesson_id})
            enrollment.check_badge()
        nxt = kw.get("next_id")
        return request.redirect("/campus/curso/%s/leccion/%s" % (course_id, nxt) if nxt else
                                "/campus/curso/%s/leccion/%s" % (course_id, lesson_id))

    @http.route("/campus/leccion/<int:lesson_id>/archivo", type="http", auth="user", sitemap=False)
    def lesson_file(self, lesson_id, **kw):
        lesson = request.env["campus.lesson"].sudo().browse(lesson_id).exists()
        if not lesson:
            raise NotFound()
        self._course(lesson.course_id.id)
        data = base64.b64decode(lesson.attachment or b"")
        return request.make_response(data, [
            ("Content-Type", "application/octet-stream"),
            ("Content-Disposition", http.content_disposition(lesson.attachment_name or "archivo"))])

    @http.route("/campus/leccion/<int:lesson_id>/ver", type="http", auth="user", sitemap=False)
    def lesson_view_file(self, lesson_id, **kw):
        """Sirve el archivo de la lección para verlo embebido (imagen, PDF, video con Range)."""
        lesson = request.env["campus.lesson"].sudo().browse(lesson_id).exists()
        if not lesson or not lesson.attachment:
            raise NotFound()
        self._course(lesson.course_id.id)
        stream = request.env["ir.binary"].sudo()._get_stream_from(
            lesson, "attachment", filename=lesson.attachment_name or "archivo",
            mimetype=lesson.attachment_mimetype())
        return stream.get_response(as_attachment=False, immutable=False)

    def _can_edit_course(self, course):
        user = request.env.user
        return user.campus_role == "admin" or (user.campus_role == "teacher" and user in course.teacher_ids)

    @http.route("/campus/leccion/<int:lesson_id>/recursos", type="http", auth="user",
                methods=["POST"], sitemap=False)
    def lesson_resources(self, lesson_id, **kw):
        """El docente o el administrador cargan video, infografía o archivo desde el campus."""
        lesson = request.env["campus.lesson"].sudo().browse(lesson_id).exists()
        if not lesson:
            raise NotFound()
        course, _enr = self._course(lesson.course_id.id)
        if not self._can_edit_course(course):
            raise NotFound()
        base = "/campus/curso/%s/leccion/%s" % (course.id, lesson.id)
        vals = {}
        for k in ("video_url", "resource_url"):
            if k in kw:
                v = (kw.get(k) or "").strip()
                if v and re.match(r"^[a-z][a-z0-9+.-]*:(?!\d)", v, re.I) and not re.match(r"^https?://", v, re.I):
                    return request.redirect(base + "?recurso=url_invalida#recursos")
                if v and not re.match(r"^https?://", v, re.I):
                    v = "https://" + v
                if v and not re.match(r"^https?://[^\s<>\"']+$", v, re.I):
                    return request.redirect(base + "?recurso=url_invalida#recursos")
                vals[k] = v or False
        if kw.get("remove_file"):
            vals.update({"attachment": False, "attachment_name": False})
        f = request.httprequest.files.get("file")
        if f and f.filename:
            data = f.read()
            if not data:
                return request.redirect(base + "?recurso=vacio#recursos")
            if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
                return request.redirect(base + "?recurso=grande#recursos")
            vals.update({"attachment": base64.b64encode(data),
                         "attachment_name": os.path.basename(f.filename)[:200]})
        if vals:
            lesson.write(vals)
        return request.redirect(base + "?recurso=ok#recursos")

    @http.route("/campus/leccion/<int:lesson_id>/practica", type="json", auth="user", sitemap=False)
    def lesson_quiz_check(self, lesson_id, question_id=0, option_id=0, **kw):
        """Corrige una pregunta del cuestionario de práctica sin exponer la clave en la página."""
        lesson = request.env["campus.lesson"].sudo().browse(int(lesson_id)).exists()
        if not lesson:
            raise NotFound()
        self._course(lesson.course_id.id)
        q = lesson.quiz_questions().filtered(lambda x: x.id == int(question_id or 0))
        if not q:
            return {"error": "Pregunta no válida"}
        opt = q.option_ids.filtered(lambda o: o.id == int(option_id or 0))
        correct = q.option_ids.filtered("is_correct")[:1]
        return {"ok": bool(opt and opt.is_correct), "correct_id": correct.id,
                "feedback": (opt.feedback if opt else "") or "", "explanation": q.explanation or ""}

    # ---------------------------------------------------------- simulador
    @http.route("/campus/curso/<int:course_id>/simulador", type="http", auth="user", sitemap=False)
    def simulator(self, course_id, **kw):
        course, enrollment = self._course(course_id)
        attempts = enrollment.attempt_ids.filtered(lambda a: a.state == "done") if enrollment else []
        return self._render("campus_pi.course_simulator", {
            "course": course, "enrollment": enrollment, "attempts": attempts, "tab": "sim",
            "can_edit": self._can_edit_course(course)})

    @http.route("/campus/curso/<int:course_id>/preguntas/importar", type="http", auth="user",
                methods=["POST"], sitemap=False)
    def import_questions(self, course_id, **kw):
        """Carga de un banco de preguntas en formato GIFT (Moodle) por el docente o el administrador."""
        course, _enr = self._course(course_id)
        if not self._can_edit_course(course):
            raise NotFound()
        from ..tools.gift import parse_gift
        base = "/campus/curso/%s/simulador" % course.id
        f = request.httprequest.files.get("gift")
        if not f or not f.filename:
            return request.redirect(base + "?gift=sin_archivo#importar")
        data = f.read()
        if len(data) > 3 * 1024 * 1024:
            return request.redirect(base + "?gift=grande#importar")
        items = parse_gift(data.decode("utf-8-sig", errors="ignore"))
        if not items:
            return request.redirect(base + "?gift=vacio#importar")
        n = request.env["campus.ai.agent"].sudo().import_question_items(
            course, items, (kw.get("domain") or "General").strip()[:120])
        return request.redirect(base + "?gift=ok&n=%d&t=%d#importar" % (n, len(items)))

    @http.route("/campus/curso/<int:course_id>/simulador/iniciar", type="http", auth="user",
                methods=["POST"], sitemap=False)
    def simulator_start(self, course_id, **kw):
        course, enrollment = self._course(course_id)
        if not enrollment:
            return request.redirect("/campus/curso/%s/simulador" % course_id)
        if not course.question_ids:
            return request.redirect("/campus/curso/%s/simulador?error=sin_preguntas" % course_id)
        attempt = request.env["campus.sim.attempt"].sudo().start(enrollment)
        return request.redirect("/campus/simulador/%s" % attempt.id)

    def _attempt(self, attempt_id):
        attempt = request.env["campus.sim.attempt"].sudo().browse(attempt_id).exists()
        if not attempt or attempt.user_id != request.env.user:
            raise NotFound()
        return attempt

    @http.route("/campus/simulador/<int:attempt_id>", type="http", auth="user", sitemap=False)
    def simulator_take(self, attempt_id, **kw):
        attempt = self._attempt(attempt_id)
        if attempt.state == "done":
            return request.redirect("/campus/simulador/%s/resultado" % attempt.id)
        deadline_ms = int(attempt.deadline.replace(tzinfo=pytz.utc).timestamp() * 1000)
        return self._render("campus_pi.simulator_take", {
            "attempt": attempt, "course": attempt.course_id, "deadline_ms": deadline_ms, "tab": "sim"})

    @http.route("/campus/simulador/<int:attempt_id>/enviar", type="http", auth="user",
                methods=["POST"], sitemap=False)
    def simulator_submit(self, attempt_id, **kw):
        attempt = self._attempt(attempt_id)
        if attempt.state != "done":
            answers = {int(k[4:]): v for k, v in kw.items() if k.startswith("ans_") and v}
            valid = {a.id: a.question_id.option_ids.ids for a in attempt.answer_ids}
            answers = {k: v for k, v in answers.items() if k in valid and int(v) in valid[k]}
            attempt.finish(answers)
        return request.redirect("/campus/simulador/%s/resultado" % attempt.id)

    @http.route("/campus/simulador/<int:attempt_id>/resultado", type="http", auth="user", sitemap=False)
    def simulator_result(self, attempt_id, **kw):
        attempt = self._attempt(attempt_id)
        cert = attempt.course_id.certification_id
        return self._render("campus_pi.simulator_result", {
            "attempt": attempt, "course": attempt.course_id, "tab": "sim",
            "passing": cert.passing_score if cert else 70.0,
            "enrollment": attempt.enrollment_id})

    # ---------------------------------------------------- tutoría virtual
    @http.route("/campus/curso/<int:course_id>/tutoria", type="http", auth="user",
                methods=["GET", "POST"], sitemap=False)
    def tutoring(self, course_id, **kw):
        course, enrollment = self._course(course_id)
        msg = None
        if request.httprequest.method == "POST" and enrollment:
            try:
                teacher = request.env["res.users"].sudo().browse(int(kw.get("teacher_id") or 0)).exists()
                request.env["campus.tutoring"].sudo().create({
                    "kind": "virtual", "course_id": course.id, "student_id": request.env.user.id,
                    "teacher_id": (teacher if teacher in course.teacher_ids else course.teacher_ids[:1]).id,
                    "name": kw.get("name") or "Tutoría", "notes": kw.get("notes"),
                    "datetime": self._to_utc(kw["datetime"]),
                    "duration_min": int(kw.get("duration_min") or 30)})
                msg = _("Tutoría solicitada. Tu docente la confirmará y recibirás el enlace aquí.")
            except (ValueError, KeyError):
                msg = _("Revisa la fecha y hora.")
        tutorings = request.env["campus.tutoring"].sudo().search([
            ("course_id", "=", course.id), ("kind", "=", "virtual"),
            ("student_id", "=", request.env.user.id)], order="datetime desc")
        return self._render("campus_pi.course_tutoring", {
            "course": course, "enrollment": enrollment, "tutorings": tutorings, "msg": msg, "tab": "tutor"})

    @http.route("/campus/tutoria/<int:tid>/gestionar", type="http", auth="user", methods=["POST"], sitemap=False)
    def tutoring_manage(self, tid, **kw):
        t = request.env["campus.tutoring"].sudo().browse(tid).exists()
        user = request.env.user
        if not t or not (user.campus_role == "admin" or user in t.course_id.teacher_ids):
            raise NotFound()
        vals = {}
        if kw.get("meeting_url"):
            vals["meeting_url"] = kw["meeting_url"]
        if kw.get("action") in ("confirmed", "done", "cancel"):
            vals["state"] = kw["action"]
            vals.setdefault("teacher_id", user.id)
        t.write(vals)
        return request.redirect("/campus")

    # ----------------------------------------------------------- tutor IA
    @http.route("/campus/curso/<int:course_id>/tutor-ia", type="http", auth="user", sitemap=False)
    def ai_tutor(self, course_id, **kw):
        course, enrollment = self._course(course_id)
        history = request.env["campus.ai.message"].sudo().search([
            ("course_id", "=", course.id), ("user_id", "=", request.env.user.id)], order="id desc", limit=40)
        sessions = request.env["campus.tutoring"].sudo().search([
            ("course_id", "=", course.id), ("kind", "=", "ia"),
            ("student_id", "=", request.env.user.id)], order="datetime desc")
        staff = self._role() in ("admin", "teacher")
        return self._render("campus_pi.course_ai_tutor", {
            "course": course, "enrollment": enrollment, "history": history.sorted("id"),
            "sessions": sessions, "tab": "ai", "prefill": kw.get("q", ""), "staff": staff,
            "insights": request.env["campus.ai.agent"].sudo().course_insights(course) if staff else None,
            "ai_label": request.env["campus.ai.agent"].sudo().provider_label()})

    @http.route("/campus/curso/<int:course_id>/tutor-ia/mensaje", type="json", auth="user", sitemap=False)
    def ai_tutor_message(self, course_id, message="", **kw):
        course, _enr = self._course(course_id)
        message = (message or "").strip()[:4000]
        if not message:
            return {"answer": ""}
        answer = request.env["campus.ai.agent"].sudo().tutor_reply(course, request.env.user, message)
        return {"answer": answer}

    @http.route("/campus/curso/<int:course_id>/tutor-ia/agendar", type="http", auth="user",
                methods=["POST"], sitemap=False)
    def ai_tutor_schedule(self, course_id, **kw):
        course, enrollment = self._course(course_id)
        try:
            dt = self._to_utc(kw["datetime"])
        except (KeyError, ValueError):
            return request.redirect("/campus/curso/%s/tutor-ia" % course_id)
        t = request.env["campus.tutoring"].sudo().create({
            "kind": "ia", "course_id": course.id, "student_id": request.env.user.id,
            "name": kw.get("name") or "Sesión con tutor IA", "notes": kw.get("notes"),
            "datetime": dt, "duration_min": int(kw.get("duration_min") or 30), "state": "confirmed"})
        t.ai_plan = request.env["campus.ai.agent"].sudo().prepare_tutoring_plan(t)
        return request.redirect("/campus/curso/%s/tutor-ia#sesiones" % course_id)

    # --------------------------------------------------- microcredenciales
    @http.route("/campus/credencial/<int:badge_id>/pdf", type="http", auth="user", sitemap=False)
    def badge_pdf(self, badge_id, **kw):
        badge = request.env["campus.badge"].sudo().browse(badge_id).exists()
        if not badge or (badge.user_id != request.env.user and request.env.user.campus_role != "admin"):
            raise NotFound()
        pdf, _t = request.env["ir.actions.report"].sudo()._render_qweb_pdf("campus_pi.report_badge", [badge.id])
        return request.make_response(pdf, [
            ("Content-Type", "application/pdf"),
            ("Content-Disposition", http.content_disposition("Microcredencial-%s.pdf" % badge.code))])

    @http.route("/campus/verificar/<string:code>", type="http", auth="public", sitemap=False)
    def verify(self, code, **kw):
        badge = request.env["campus.badge"].sudo().search([("code", "=", (code or "").upper())], limit=1)
        return request.render("campus_pi.verify_page", {"badge": badge, "code": code})

    # ---------------------------------------------------- propuesta valor
    @http.route("/campus/valor", type="http", auth="public", sitemap=False)
    def value(self, **kw):
        return self._render("campus_pi.value_page")

    # -------------------------------------------------------------- admin
    @http.route("/campus/admin/crear-curso", type="http", auth="user", methods=["GET", "POST"], sitemap=False)
    def admin_create_course(self, **kw):
        redirect = self._require("admin")
        if redirect:
            return redirect
        env = request.env
        error = None
        if request.httprequest.method == "POST":
            f = request.httprequest.files.get("syllabus")
            try:
                if not f or not f.filename:
                    raise UserError(_("Cargue el syllabus (PDF, DOCX o TXT)."))
                if not f.filename.lower().endswith((".pdf", ".docx", ".txt")):
                    raise UserError(_("Formato no admitido: use PDF, DOCX o TXT."))
                if kw.get("date_start") and kw.get("date_end") and kw["date_end"] < kw["date_start"]:
                    raise UserError(_("La fecha de fin no puede ser anterior a la fecha de inicio."))
                data = f.read()
                if not data:
                    raise UserError(_("El archivo del syllabus está vacío."))
                if len(data) > 15 * 1024 * 1024:
                    raise UserError(_("El syllabus supera 15 MB."))
                plist = request.httprequest.form.getlist
                cert_val = kw.get("certification_id") or ""
                job = env["campus.agent.job"].sudo().create({
                    "name": (kw.get("name") or f.filename)[:200],
                    "syllabus_file": base64.b64encode(data), "syllabus_filename": os.path.basename(f.filename),
                    "certification_id": int(cert_val) if cert_val.isdigit() else False,
                    "deep_research": bool(kw.get("deep_research")),
                    "user_id": request.env.user.id,
                    "params": {
                        "name": kw.get("name"), "cert_mode": "auto" if cert_val == "auto" else "fixed",
                        "date_start": kw.get("date_start") or False, "date_end": kw.get("date_end") or False,
                        "modality": kw.get("modality") or "virtual", "instructions": (kw.get("instructions") or "")[:4000],
                        "teacher_ids": [int(x) for x in plist("teacher_ids") if x.isdigit()],
                        "student_ids": [int(x) for x in plist("student_ids") if x.isdigit()],
                        "use_ai": True,
                    },
                })
                job.action_start()
                return request.redirect("/campus/admin/agente/%s" % job.id)
            except UserError as e:
                error = e.args[0]
            except Exception as e:  # noqa: BLE001
                _logger.exception("Error iniciando el agente")
                error = _("El agente no pudo iniciar: %s") % e
        return self._render("campus_pi.admin_create_course", {
            "jobs": env["campus.agent.job"].sudo().search([], limit=8),
            "ai_label": env["campus.ai.agent"].sudo().provider_label(),
            "ai_search": env["campus.ai.agent"].sudo().has_web_search(),
            "certs": env["campus.certification"].sudo().search([]),
            "teachers": env["res.users"].sudo().search([("groups_id", "in", env.ref("campus_pi.group_campus_teacher").id)]),
            "students": env["res.users"].sudo().search([("groups_id", "in", env.ref("campus_pi.group_campus_student").id)]),
            "error": error})

    # ------------------------------------------------------ proveedor de IA
    @http.route("/campus/admin/ia", type="http", auth="user", methods=["GET", "POST"], sitemap=False)
    def admin_ai_settings(self, **kw):
        redirect = self._require("admin")
        if redirect:
            return redirect
        from ..tools import llm
        agent = request.env["campus.ai.agent"].sudo()
        ICP = request.env["ir.config_parameter"].sudo()
        msg, test = None, None
        if request.httprequest.method == "POST":
            if kw.get("action") == "save":
                ICP.set_param("campus_pi.ai_provider", kw.get("provider") if kw.get("provider") in llm.PROVIDERS else "")
                for prov, (_env, param) in agent.KEY_PARAMS.items():
                    val = (kw.get("key_%s" % prov) or "").strip()
                    if kw.get("clear_%s" % prov):
                        ICP.set_param(param, False)
                    elif val:
                        ICP.set_param(param, val)
                ICP.set_param("campus_pi.ai_model", (kw.get("model") or "").strip() or False)
                url = (kw.get("base_url") or "").strip()
                ICP.set_param("campus_pi.ai_base_url", url if url.startswith("http") else False)
                msg = "Configuración guardada."
            elif kw.get("action") == "test":
                if not agent.is_enabled():
                    test = {"ok": False, "text": "No hay un proveedor con clave configurada."}
                else:
                    t0 = datetime.now()
                    try:
                        out = agent._call("Responde en español, en una sola frase.",
                                          [{"role": "user", "content": "¿Qué es la confidencialidad en seguridad de la información?"}],
                                          max_tokens=200)
                        test = {"ok": bool(out.strip()), "text": out.strip()[:400],
                                "secs": round((datetime.now() - t0).total_seconds(), 1)}
                    except Exception as e:  # noqa: BLE001
                        test = {"ok": False, "text": str(e)[:400]}
        status = []
        for prov, (env_name, param) in agent.KEY_PARAMS.items():
            key = agent._key_for(prov)
            status.append({"code": prov, "label": llm.PROVIDERS[prov]["label"],
                           "configured": bool(key), "from_env": bool(os.environ.get(env_name)),
                           "hint": ("…" + key[-4:]) if key and key != "local" else "",
                           "model": llm.PROVIDERS[prov]["model"], "search": llm.PROVIDERS[prov]["search"]})
        return self._render("campus_pi.admin_ai_settings", {
            "status": status, "msg": msg, "test": test, "active": agent.provider_label(),
            "provider": ICP.get_param("campus_pi.ai_provider") or "",
            "model": ICP.get_param("campus_pi.ai_model") or "",
            "base_url": ICP.get_param("campus_pi.ai_base_url") or ""})

    def _job(self, job_id):
        job = request.env["campus.agent.job"].sudo().browse(job_id).exists()
        if not job:
            raise NotFound()
        return job

    @http.route("/campus/admin/agente/<int:job_id>", type="http", auth="user", sitemap=False)
    def admin_agent_job(self, job_id, **kw):
        redirect = self._require("admin")
        if redirect:
            return redirect
        from ..models.agent_job import STAGES
        return self._render("campus_pi.admin_agent_job", {"job": self._job(job_id), "stages": STAGES})

    @http.route("/campus/admin/agente/<int:job_id>/estado", type="json", auth="user", sitemap=False)
    def admin_agent_job_state(self, job_id, **kw):
        if self._role() != "admin":
            raise NotFound()
        job = self._job(job_id)
        return {"state": job.state, "progress": job.progress, "stage": job.stage, "log": job.log or "",
                "error": job.error or "", "stale": bool(job.is_stale()),
                "course_url": "/campus/curso/%s" % job.course_id.id if job.course_id and job.state == "done" else ""}

    @http.route("/campus/admin/agente/<int:job_id>/reintentar", type="http", auth="user",
                methods=["POST"], sitemap=False)
    def admin_agent_job_retry(self, job_id, **kw):
        redirect = self._require("admin")
        if redirect:
            return redirect
        job = self._job(job_id)
        if job.state == "error" or job.is_stale():
            job.action_retry()
        return request.redirect("/campus/admin/agente/%s" % job.id)

    @http.route("/campus/admin/cursos", type="http", auth="user", sitemap=False)
    def admin_courses(self, **kw):
        redirect = self._require("admin")
        if redirect:
            return redirect
        env = request.env
        return self._render("campus_pi.admin_courses", {
            "courses": env["campus.course"].sudo().search([]),
            "students": env["res.users"].sudo().search([("groups_id", "in", env.ref("campus_pi.group_campus_student").id)]),
            "nuevo": int(kw.get("nuevo") or 0), "msg": kw.get("msg")})

    @http.route("/campus/admin/curso/<int:course_id>/guardar", type="http", auth="user",
                methods=["POST"], sitemap=False)
    def admin_course_save(self, course_id, **kw):
        redirect = self._require("admin")
        if redirect:
            return redirect
        course = request.env["campus.course"].sudo().browse(course_id).exists()
        if not course:
            raise NotFound()
        vals = {}
        for k in ("date_start", "date_end"):
            if kw.get(k):
                vals[k] = kw[k]
        if kw.get("state") in ("draft", "published", "closed"):
            vals["state"] = kw["state"]
        course.write(vals)
        ids = [int(x) for x in request.httprequest.form.getlist("student_ids")]
        if ids:
            course.enroll_users(request.env["res.users"].sudo().browse(ids))
        return request.redirect("/campus/admin/cursos?msg=Curso%20actualizado")

    @http.route("/campus/admin/estudiante/crear", type="http", auth="user", methods=["POST"], sitemap=False)
    def admin_student_create(self, **kw):
        redirect = self._require("admin")
        if redirect:
            return redirect
        email = (kw.get("email") or "").strip().lower()
        if email and kw.get("name") and kw.get("password"):
            Users = request.env["res.users"].sudo()
            if not Users.search_count([("login", "=", email)]):
                Users.with_context(no_reset_password=True).create({
                    "name": kw["name"], "login": email, "email": email, "password": kw["password"],
                    "tz": "America/Bogota",
                    "groups_id": [(6, 0, [request.env.ref("campus_pi.group_campus_student").id])]})
        return request.redirect("/campus/admin/cursos?msg=Estudiante%20creado")
