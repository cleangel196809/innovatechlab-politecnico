# -*- coding: utf-8 -*-
"""Voz de las presentaciones, descargas institucionales, actividad interactiva e importación de usuarios."""
import base64
import logging
import re

from urllib.parse import quote
from werkzeug.exceptions import NotFound

from odoo.exceptions import UserError

from odoo import http
from odoo.http import request

from .main import Campus as _Campus, _upload
from ..tools import people as people_tools

_logger = logging.getLogger(__name__)


def _slug(t):
    return re.sub(r"[^\w\- ]+", "", t or "material").strip()[:80] or "material"


class CampusMaterials(_Campus):

    def _lesson(self, lesson_id):
        lesson = request.env["campus.lesson"].sudo().browse(int(lesson_id)).exists()
        if not lesson:
            raise NotFound()
        course, enrollment = self._course(lesson.course_id.id)
        return lesson, course, enrollment

    @http.route("/campus/leccion/<int:lesson_id>/voz/<int:index>", type="http", auth="user", sitemap=False)
    def lesson_voice(self, lesson_id, index, **kw):
        lesson, _c, _e = self._lesson(lesson_id)
        try:
            mp3 = lesson.voice_mp3(index)
        except Exception as e:  # noqa: BLE001
            _logger.warning("Voz neuronal no disponible (lección %s): %s", lesson_id, e)
            mp3 = None
        if not mp3:
            # el navegador usa su propia voz
            return request.make_response("", status=503, headers=[("Cache-Control", "no-store")])
        return request.make_response(mp3, [("Content-Type", "audio/mpeg"), ("Content-Length", str(len(mp3))),
                                           ("Cache-Control", "private, max-age=604800")])

    @http.route("/campus/leccion/<int:lesson_id>/pptx", type="http", auth="user", sitemap=False)
    def lesson_pptx(self, lesson_id, **kw):
        lesson, _c, _e = self._lesson(lesson_id)
        try:
            data = lesson.pptx_bytes()
        except ImportError:
            return request.make_response("El servidor no tiene python-pptx instalado.", status=501)
        return request.make_response(data, [
            ("Content-Type", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
            ("Content-Disposition", http.content_disposition("%s.pptx" % _slug(lesson.section_id.name)))])

    @http.route("/campus/seccion/<int:section_id>/paquete", type="http", auth="user", sitemap=False)
    def section_package(self, section_id, **kw):
        sec = request.env["campus.section"].sudo().browse(int(section_id)).exists()
        if not sec:
            raise NotFound()
        course, _e = self._course(sec.course_id.id)
        if not self._can_edit_course(course):
            raise NotFound()
        try:
            data = sec.package_zip()
        except ImportError:
            return request.make_response("El servidor no tiene python-docx/python-pptx instalados.", status=501)
        return request.make_response(data, [
            ("Content-Type", "application/zip"),
            ("Content-Disposition", http.content_disposition("Paquete %s.zip" % _slug(sec.name)))])

    @http.route("/campus/leccion/<int:lesson_id>/actividad", type="json", auth="user", sitemap=False)
    def lesson_activity_check(self, lesson_id, question_id=0, option_id=0, **kw):
        lesson, _c, _e = self._lesson(lesson_id)
        qs = lesson.activity_json or []
        qi, oi = int(question_id or 0), int(option_id or 0)
        if not 0 <= qi < len(qs) or not isinstance(qs[qi], dict):
            return {"error": "Pregunta no válida"}
        ops = qs[qi].get("opciones") or []
        if not 0 <= oi < len(ops):
            return {"error": "Opción no válida"}
        right = next((k for k, o in enumerate(ops) if o.get("correcta")), 0)
        return {"ok": oi == right, "correct_id": right, "feedback": ops[oi].get("retro") or "", "explanation": ""}

    # ------------------------------------------------------ usuarios por Excel
    @http.route("/campus/admin/usuarios/plantilla.xlsx", type="http", auth="user", sitemap=False)
    def users_template(self, **kw):
        redirect = self._require("admin")
        if redirect:
            return redirect
        role = "docentes" if kw.get("rol") == "teacher" else "estudiantes"
        return request.make_response(people_tools.template_xlsx(role), [
            ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("Content-Disposition", http.content_disposition("plantilla_%s.xlsx" % role))])

    @http.route("/campus/admin/usuarios/importar", type="http", auth="user", methods=["POST"], sitemap=False)
    def users_import(self, **kw):
        redirect = self._require("admin")
        if redirect:
            return redirect
        role = "teacher" if kw.get("role") == "teacher" else "student"
        course = request.env["campus.course"].sudo().browse(int(kw.get("course_id") or 0)).exists()
        pwd = (kw.get("password") or "").strip()
        values = {"role_label": "docentes" if role == "teacher" else "estudiantes", "course": course,
                  "results": [], "errors": [], "error": None, "xlsx_b64": None}
        f = _upload("file", kw)
        if not f or not getattr(f, "filename", None):
            values["error"] = "Seleccione el archivo de Excel (.xlsx) o CSV."
            return self._render("campus_pi.admin_import_result", values)
        try:
            people, errors = people_tools.parse_people(f.read(), f.filename)
        except ValueError as e:
            values["error"] = str(e)
            return self._render("campus_pi.admin_import_result", values)
        if not people and not errors:
            values["error"] = "El archivo no tiene filas con nombre y correo."
        if len(people) > 1000:
            values["error"] = "Máximo 1.000 personas por archivo."
            people = []
        results = request.env["campus.user.import"].sudo().import_people(people, role, course or None, pwd or None)
        values.update({"results": results, "errors": errors})
        if results:
            values["xlsx_b64"] = base64.b64encode(people_tools.credentials_xlsx(results)).decode()
        return self._render("campus_pi.admin_import_result", values)

    # ------------------------------------------------------ regenerar cursos
    @http.route("/campus/admin/curso/<int:course_id>/regenerar", type="http", auth="user", methods=["POST"],
                sitemap=False)
    def course_regenerate(self, course_id, **kw):
        redirect = self._require("admin")
        if redirect:
            return redirect
        from .main import _uploads
        course = request.env["campus.course"].sudo().browse(course_id).exists()
        if not course:
            raise NotFound()
        if not request.env["campus.ai.agent"].sudo().is_enabled():
            return request.redirect("/campus/admin/cursos?msg=Configure%20un%20proveedor%20de%20IA%20para%20regenerar")
        try:
            jobs = course.action_regenerate(instructions=(kw.get("instructions") or "").strip() or None,
                                            files=_uploads("materials", kw), deep_research=bool(kw.get("deep_research")),
                                            economy=bool(kw.get("economy")))
        except UserError as e:
            return request.redirect("/campus/admin/cursos?msg=" + quote(e.args[0]))
        return request.redirect("/campus/admin/agente/%s" % jobs[:1].id)

    @http.route("/campus/admin/cursos/regenerar-todos", type="http", auth="user", methods=["POST"], sitemap=False)
    def courses_regenerate_all(self, **kw):
        redirect = self._require("admin")
        if redirect:
            return redirect
        if not request.env["campus.ai.agent"].sudo().is_enabled():
            return request.redirect("/campus/admin/cursos?msg=Configure%20un%20proveedor%20de%20IA%20para%20regenerar")
        jobs = request.env["campus.course"].sudo().regenerate_all(deep_research=bool(kw.get("deep_research")),
                                                                  economy=bool(kw.get("economy")))
        request.env["ir.config_parameter"].sudo().set_param("campus_pi.regen_jobs", ",".join(str(i) for i in jobs.ids))
        request.env["ir.config_parameter"].sudo().set_param("campus_pi.regen_pending", False)
        return request.redirect("/campus/admin/agente/%s" % jobs[:1].id if jobs else "/campus/admin/cursos")
