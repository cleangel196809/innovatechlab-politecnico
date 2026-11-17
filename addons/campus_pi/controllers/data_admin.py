# -*- coding: utf-8 -*-
"""Administración de la base de datos desde el campus: listar, buscar, crear, editar y eliminar (CRUD)
los registros principales sin entrar al backend de Odoo. Solo administradores del campus."""
import logging
from datetime import date, datetime

from werkzeug.exceptions import NotFound

from odoo import fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.tools import html_sanitize

from .materials import CampusMaterials as _Campus

_logger = logging.getLogger(__name__)
PAGE = 40

# clave: (modelo, título, columnas de la lista, campos excluidos del formulario)
TABLES = {
    "usuarios": ("res.users", "Usuarios", ["name", "login", "campus_role", "phone", "mobile", "active"], []),
    "cursos": ("campus.course", "Cursos", ["name", "state", "date_start", "date_end", "certification_id"],
               ["syllabus_text", "ai_log", "sources_html", "tutor_prompt"]),
    "secciones": ("campus.section", "Secciones / núcleos", ["name", "course_id", "sequence"], ["kit_json"]),
    "lecciones": ("campus.lesson", "Lecciones", ["name", "section_id", "lesson_type", "sequence", "duration_min"],
                  ["slides_json", "infographic_json", "activity_json"]),
    "inscripciones": ("campus.enrollment", "Inscripciones", ["user_id", "course_id", "create_date"], []),
    "preguntas": ("campus.question", "Banco de preguntas", ["name", "course_id", "section_id", "domain"], []),
    "opciones": ("campus.question.option", "Opciones de respuesta", ["name", "question_id", "is_correct"], []),
    "certificaciones": ("campus.certification", "Certificaciones", ["name", "provider", "exam_code"], []),
    "microcredenciales": ("campus.badge", "Microcredenciales", ["code", "create_date"], []),
    "tutorias": ("campus.tutoring", "Tutorías", ["course_id", "datetime", "state"], []),
    "material": ("campus.material", "Material del docente", ["name", "course_id", "nucleo", "kind"], ["text"]),
}
SKIP = {"id", "create_uid", "write_uid", "write_date", "display_name", "__last_update", "message_ids",
        "message_follower_ids", "activity_ids", "website_message_ids", "message_main_attachment_id", "password",
        "new_password", "groups_id", "company_ids", "company_id", "partner_id", "action_id", "signature",
        "campus_reset_hash", "campus_reset_expiry", "access_token"}
EDITABLE = ("char", "text", "html", "integer", "float", "monetary", "boolean", "selection", "date", "datetime",
            "many2one", "many2many")
USER_FIELDS = ["name", "login", "email", "phone", "mobile", "active", "campus_must_change_password"]


def _table(key):
    if key not in TABLES:
        raise NotFound()
    model, title, cols, excl = TABLES[key]
    if model not in request.env:
        raise NotFound()
    return request.env[model].sudo(), title, cols, excl


def _form_fields(Model, key, excl):
    if key == "usuarios":
        names = USER_FIELDS
    else:
        names = [n for n, f in Model._fields.items()
                 if n not in SKIP and n not in excl and f.type in EDITABLE and (f.store or f.type == "many2many")
                 and not f.readonly and not f.related and not (f.compute and not f.inverse and not f.store)
                 and not n.startswith("message_")]
    out = []
    for n in names:
        f = Model._fields.get(n)
        if not f:
            continue
        item = {"name": n, "label": f.string, "type": f.type, "required": f.required, "help": f.help or ""}
        if f.type == "selection":
            sel = f.selection(Model) if callable(f.selection) else f.selection
            item["options"] = [(str(k), v) for k, v in (sel or [])]
        if f.type in ("many2one", "many2many"):
            Co = request.env[f.comodel_name].sudo()
            count = Co.search_count([])
            item["comodel"] = f.comodel_name
            item["options"] = [(r.id, r.display_name) for r in Co.search([], limit=300)] if count <= 300 else None
        out.append(item)
    return out


def _fmt(rec, name):
    f = rec._fields.get(name)
    if not f:
        return ""
    v = rec[name]
    if f.type == "many2one":
        return v.display_name or ""
    if f.type in ("one2many", "many2many"):
        return ", ".join(v.mapped("display_name")[:4]) + (" …" if len(v) > 4 else "")
    if f.type == "selection":
        sel = f.selection(rec) if callable(f.selection) else f.selection
        return dict(sel or []).get(v, v or "")
    if f.type == "boolean":
        return "✔" if v else "—"
    if isinstance(v, datetime):
        return fields.Datetime.context_timestamp(rec, v).strftime("%Y-%m-%d %H:%M")
    if isinstance(v, date):
        return v.isoformat()
    return (str(v) if v not in (False, None) else "")[:120]


def _value(item, raw, form):
    t = item["type"]
    if t == "boolean":
        return bool(raw)
    if t == "many2many":
        return [(6, 0, [int(x) for x in form.getlist(item["name"]) if str(x).isdigit()])]
    raw = (raw or "").strip() if isinstance(raw, str) else raw
    if raw in ("", None):
        return False
    if t == "integer":
        return int(raw)
    if t in ("float", "monetary"):
        return float(str(raw).replace(",", "."))
    if t == "many2one":
        return int(raw)
    if t == "datetime":
        return str(raw).replace("T", " ")[:19] + (":00" if len(str(raw)) == 16 else "")
    if t == "html":
        return html_sanitize(raw)
    return raw


class CampusDataAdmin(_Campus):

    @http.route("/campus/admin/datos", type="http", auth="user", sitemap=False)
    def data_home(self, **kw):
        redirect = self._require("admin")
        if redirect:
            return redirect
        counts = []
        for key, (model, title, _c, _e) in TABLES.items():
            if model in request.env:
                counts.append({"key": key, "title": title, "model": model,
                               "count": request.env[model].sudo().with_context(active_test=False).search_count(
                                   self._base_domain(key))})
        return self._render("campus_pi.data_home", {"tables": counts})

    def _base_domain(self, key):
        if key == "usuarios":
            env = request.env
            gids = [env.ref("campus_pi.group_campus_%s" % g).id for g in ("admin", "teacher", "student")]
            return [("groups_id", "in", gids)]
        return []

    @http.route("/campus/admin/datos/<string:key>", type="http", auth="user", sitemap=False)
    def data_list(self, key, q="", page=1, **kw):
        redirect = self._require("admin")
        if redirect:
            return redirect
        Model, title, cols, excl = _table(key)
        Model = Model.with_context(active_test=False)
        domain = list(self._base_domain(key))
        if q:
            domain += [(Model._rec_name or "name", "ilike", q)] if (Model._rec_name or "name") in Model._fields else []
        page = max(1, int(page or 1))
        total = Model.search_count(domain)
        recs = Model.search(domain, limit=PAGE, offset=(page - 1) * PAGE)
        cols = [c for c in cols if c in Model._fields]
        rows = [{"id": r.id, "cells": [_fmt(r, c) for c in cols]} for r in recs]
        return self._render("campus_pi.data_list", {
            "key": key, "title": title, "cols": [Model._fields[c].string for c in cols], "rows": rows, "q": q,
            "page": page, "pages": max(1, (total + PAGE - 1) // PAGE), "total": total, "msg": kw.get("msg"),
            "error": kw.get("error")})

    @http.route(["/campus/admin/datos/<string:key>/nuevo", "/campus/admin/datos/<string:key>/<int:rid>"],
                type="http", auth="user", methods=["GET", "POST"], sitemap=False)
    def data_form(self, key, rid=None, **kw):
        redirect = self._require("admin")
        if redirect:
            return redirect
        Model, title, _cols, excl = _table(key)
        rec = Model.with_context(active_test=False).browse(rid).exists() if rid else Model.browse()
        if rid and not rec:
            raise NotFound()
        items = _form_fields(Model, key, excl)
        error = None
        if request.httprequest.method == "POST":
            form = request.httprequest.form
            try:
                vals = {}
                for it in items:
                    if it["type"] == "many2many" or it["name"] in form or it["type"] == "boolean":
                        vals[it["name"]] = _value(it, form.get(it["name"]), form)
                with request.env.cr.savepoint():
                    if key == "usuarios":
                        rec = self._save_user(rec, vals, kw)
                    elif rec:
                        rec.write(vals)
                    else:
                        rec = Model.create(vals)
                return request.redirect("/campus/admin/datos/%s?msg=Registro%%20guardado" % key)
            except (UserError, ValidationError, ValueError) as e:
                error = str(e.args[0] if e.args else e)
            except Exception as e:  # noqa: BLE001
                _logger.exception("CRUD %s", key)
                error = "No se pudo guardar: %s" % str(e)[:300]
        values = {}
        for it in items:
            v = rec[it["name"]] if rec else False
            if it["type"] == "many2one":
                v = v.id if v else ""
                if it["options"] is None and rec and rec[it["name"]]:
                    it["current"] = rec[it["name"]].display_name
            elif it["type"] == "many2many":
                v = v.ids if v else []
            elif it["type"] == "datetime" and v:
                v = fields.Datetime.to_string(v).replace(" ", "T")[:16]
            elif it["type"] == "date" and v:
                v = v.isoformat()
            values[it["name"]] = "" if v is False and it["type"] not in ("boolean",) else v
        role = rec.campus_role if (key == "usuarios" and rec) else "student"
        return self._render("campus_pi.data_form", {
            "key": key, "title": title, "rec": rec, "items": items, "values": values, "error": error, "role": role})

    def _save_user(self, rec, vals, kw):
        from ..models.user_import import default_password
        env = request.env
        groups = {g: env.ref("campus_pi.group_campus_%s" % g) for g in ("admin", "teacher", "student")}
        role = kw.get("campus_role_set") or "student"
        vals.setdefault("email", vals.get("login"))
        Users = env["res.users"].sudo().with_context(no_reset_password=True)
        if not rec:
            vals.update({"password": default_password(env), "campus_must_change_password": True, "tz": "America/Bogota",
                         "groups_id": [(6, 0, [groups.get(role, groups["student"]).id])]})
            return Users.create(vals)
        rec.write(vals)
        if role in groups and rec.campus_role != role:
            portal = env.ref("base.group_portal")
            internal = env.ref("base.group_user")
            ops = [(3, g.id) for g in groups.values()]
            if role == "student":
                ops += [(3, internal.id), (4, groups["student"].id)]
            else:
                ops += [(3, portal.id), (4, groups[role].id)]
            rec.write({"groups_id": ops})
        if kw.get("reset_password"):
            rec.campus_reset_to_default()
        return rec

    @http.route("/campus/admin/datos/<string:key>/<int:rid>/eliminar", type="http", auth="user", methods=["POST"],
                sitemap=False)
    def data_delete(self, key, rid, **kw):
        redirect = self._require("admin")
        if redirect:
            return redirect
        Model, _t, _c, _e = _table(key)
        rec = Model.with_context(active_test=False).browse(rid).exists()
        if not rec:
            raise NotFound()
        if key == "usuarios" and rec == request.env.user:
            return request.redirect("/campus/admin/datos/usuarios?error=No%20puede%20eliminar%20su%20propio%20usuario")
        try:
            with request.env.cr.savepoint():
                if key == "usuarios":
                    rec.write({"active": False})  # los usuarios se archivan: conservan historial y microcredenciales
                else:
                    rec.unlink()
        except Exception as e:  # noqa: BLE001
            from urllib.parse import quote
            return request.redirect("/campus/admin/datos/%s?error=%s" % (key, quote("No se pudo eliminar: %s" % str(e)[:200])))
        return request.redirect("/campus/admin/datos/%s?msg=%s" % (
            key, "Usuario%20archivado" if key == "usuarios" else "Registro%20eliminado"))
