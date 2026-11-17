# -*- coding: utf-8 -*-
{
    "name": "InnovaTech Lab · Campus PI",
    "summary": "Plataforma de innovación tecnológica y laboratorio de capacitación "
               "para obtener certificaciones internacionales (Politécnico Internacional)",
    "description": """
Campus virtual de microcertificaciones con agentes de IA
========================================================
* Login institucional y dashboard por rol (Administrador, Docente, Estudiante)
* Agente de diseño instruccional: crea el curso a partir del syllabus
* Lecciones por núcleos (Inicio, Núcleos, Cierre) tipo aula virtual PI
* Simulador de examen de certificación internacional con analítica por dominio
* Tutoría virtual con docente y tutoría con agente de IA (Claude)
* Microcredenciales verificables públicamente
* Presentaciones y videos con el formato institucional, voz neuronal natural y descarga en PowerPoint
* Paquete del núcleo en Word con los formatos de la Unidad Virtual (lectura, bibliografía, guion, actividad H5P, infografía y caso integrador)
* Carga masiva de estudiantes y docentes desde Excel (nombre, correo y WhatsApp)
* Administración de la base de datos (CRUD) desde el campus
* Contraseña inicial Poli2026* con cambio obligatorio y recuperación por correo
* Material del curso opcional en cualquier formato (también .zip) como fuente del agente, y regeneración de cursos
""",
    "version": "17.0.1.8.0",
    "category": "Education",
    "author": "InnovaTech Lab - Politécnico Internacional",
    "website": "https://github.com/cleangel196809/innovatechlab-politecnico",
    "license": "LGPL-3",
    "depends": ["base", "web", "mail"],
    "data": [
        "security/campus_security.xml",
        "security/ir.model.access.csv",
        "data/config_data.xml",
        "data/certification_data.xml",
        "data/users_data.xml",
        "data/course_ia_data.xml",
        "data/course_backend_data.xml",
        "data/course_frontend_data.xml",
        "data/questions_data.xml",
        "data/enrollment_data.xml",
        "report/certificate_report.xml",
        "wizard/gift_import_views.xml",
        "views/certification_views.xml",
        "views/course_views.xml",
        "views/question_views.xml",
        "views/activity_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
        "views/templates_layout.xml",
        "views/templates_login.xml",
        "views/templates_dashboard.xml",
        "views/templates_lesson_material.xml",
        "views/templates_course.xml",
        "views/templates_admin.xml",
        "views/templates_value.xml",
        "views/templates_data.xml",
    ],
    "assets": {
        "campus_pi.assets_campus": [
            "campus_pi/static/src/css/campus.css",
            "campus_pi/static/src/js/campus.js",
        ],
        "web.assets_frontend": [
            "campus_pi/static/src/css/login.css",
        ],
    },
    "post_init_hook": "post_init_hook",
    "application": True,
    "installable": True,
}
