# InnovaTech Lab · Campus PI

**Plataforma de innovación tecnológica y laboratorio de capacitación para obtener certificaciones internacionales** — Politécnico Internacional.

Módulo **Odoo 17 Community** (`addons/campus_pi`) con base de datos **PostgreSQL gratuita (Neon)**, despliegue en **Render** y agentes de IA con **Anthropic Claude**.

---

## 1. Qué incluye

| Bloque | Descripción |
|---|---|
| Login institucional | `/campus/login` con el isologo del PI, el texto institucional y los campos usuario y contraseña. `/web/login` también lleva la marca. |
| Dashboard por rol | **Administrador** (módulos y KPI), **Docente** (cursos, sesiones, tutorías, estudiantes en riesgo) y **Estudiante** (saludo + **Mis cursos**). |
| Agente de diseño instruccional | El administrador sube el syllabus (PDF/DOCX/TXT), elige la certificación, las fechas, los docentes y los estudiantes. El agente genera los núcleos, las lecciones, las sesiones virtuales y presenciales asistidas por IA (con guion), el cronograma y el banco del simulador. |
| Aula del curso (modelo aula virtual PI) | Secciones Inicio, Núcleos 1–4 y Cierre, con un índice lateral y avance por lección. Menú del curso: **Lecciones · Simulador de certificación · Agendar tutoría virtual · Tutoría con IA**. |
| Simulador | Examen aleatorio y cronometrado con el puntaje mínimo de la certificación, resultados por dominio y revisión pregunta a pregunta. |
| Tutor IA | Chat con el contexto del curso y los dominios débiles del estudiante. También permite agendar sesiones con IA (el agente prepara un plan previo). |
| Microcredenciales | Se emiten automáticamente al completar el 100 % de las lecciones y aprobar el simulador. Se descargan en PDF y tienen verificación pública en `/campus/verificar/<código>`. |
| Migración desde Moodle | Importación de bancos de preguntas en formato **GIFT**. |
| Valor diferencial | Página `/campus/valor`: 6 diferenciadores, un comparativo honesto con Moodle y un proceso de piloto para demostrar el valor. |

### Cursos precargados

| Curso | Certificación objetivo | Referente |
|---|---|---|
| Inteligencia Artificial Aplicada y Agentes de IA | Microsoft **AI-901** Azure AI Fundamentals | IBM AI Engineering (Coursera) |
| Desarrollo Backend con Java y Spring Boot | Oracle **1Z0-830** Java SE 21 Developer | Syllabus PI-GA-FT-141 (lecturas, casos y cuestionarios GIFT reales) |
| Desarrollo de Aplicaciones Web Front-End y Multimedia | OpenEDG **JSE-40-01** | Syllabus PI-GA-FT-141 + Meta Front-End Developer |

### Usuarios de prueba (contraseña `Oddo123456`)

| Rol | Usuario |
|---|---|
| Administrador | administrador.prueba@pi.edu.co |
| Administrador | gustavo.contreras@pi.edu.co |
| Docente | docente.prueba@pi.edu.co *(creado para poder probar el rol)* |
| Estudiante (IA + Backend) | prueba.estudiante@pi.edu.co |
| Estudiante (Backend + Front-End) | prueba.estudiante2@pi.edu.co |

> ⚠️ Este repositorio es **público**: cualquiera que lo lea conoce estas contraseñas. Cámbielas apenas haya datos reales.

---

## 1.1 Agente de creación de cursos (v17.0.1.2.0)

**Campus → Crear curso con IA**: se sube el syllabus PI-GA-FT-141 (DOCX recomendado; también PDF o TXT) y el agente
trabaja **en segundo plano** mostrando su avance en vivo (`/campus/admin/agente/<id>`):

1. **Lee el syllabus**: identificación, competencia, resultado de aprendizaje, objetivos 3.4.x, tabla de alineación
   curricular (núcleos, temas, objetivo, estrategias, criterios), criterios de evaluación, bibliografía y cibergrafía.
   Con PDF/TXT y API key, Claude reconstruye la tabla de alineación.
2. **Certificación**: la elegida, la detectada en el syllabus (código o nombre) o la que encuentre la investigación
   (la crea con dominios y pesos).
3. **Investigación profunda en la web** (Claude + herramienta `web_search`): versión vigente de la certificación,
   novedades y recursos por núcleo, con fuentes registradas en el curso.
4. **Estructura y cronograma**: Inicio, un núcleo por cada núcleo del syllabus y Cierre, con fechas.
5. **Contenido por núcleo** (en paralelo): lectura con fuentes, presentación (diapositivas), infografía, guion de video,
   actividad formativa, laboratorio, evaluación según el instrumento del syllabus (rúbrica BUENO/REGULAR/INSUFICIENTE),
   sesión virtual con agenda, sesión presencial asistida por IA con guion y cuestionario con preguntas propias.
6. **Banco del simulador** por dominio, proporcional al peso de cada dominio.
7. **Inicio y cierre**: guía del estudiante (ruta, matriz de evaluación, entorno, acuerdos), ruta de certificación,
   diagnóstico, video de bienvenida, autoevaluación, simulacro y plan para el examen.
8. **Fuentes y bitácora** del agente en el curso; inscripción de estudiantes.

Sin API key todo se arma solo con el syllabus (sin investigación ni preguntas nuevas). Si una etapa de IA falla, el
agente continúa con el contenido base y lo deja anotado en la bitácora.
Requisito para la investigación: tener habilitada la búsqueda web en la organización de la Consola de Claude.

Pruebas: `tests/e2e/agent_e2e.js`, `agent_fail.js` y `mock_anthropic.py` (simula la API de Anthropic, incluida la
búsqueda web, para probar el agente sin gastar créditos: `CAMPUS_ANTHROPIC_URL=http://127.0.0.1:9911/v1/messages`).

## 2. Paso a paso: de cero a Render

### Paso 1 · Crear la base de datos gratuita en Neon
1. Entre a <https://neon.tech> y cree una cuenta con GitHub.
2. Haga clic en **New project**. Nombre: `innovatechlab`. Postgres 16. Región: **AWS US East (N. Virginia)**.
3. En **Connection details** desactive *Connection pooling* y copie la cadena **directa**:
   `postgresql://neondb_owner:XXXX@ep-xxxx.us-east-1.aws.neon.tech/neondb?sslmode=require`
4. Guárdela: es su `DATABASE_URL`.

### Paso 2 · Obtener la API key de Anthropic
1. Entre a <https://console.anthropic.com> → **API Keys** → **Create key**.
2. Cargue saldo (es de pago por uso) y fije un límite de gasto mensual.
3. Guarde la clave (`sk-ant-...`): es su `ANTHROPIC_API_KEY`.
   *Sin clave, el campus funciona igual en “modo sin IA”.*

### Paso 3 · Subir el código a GitHub
```bash
git clone https://github.com/cleangel196809/innovatechlab-politecnico.git
cd innovatechlab-politecnico
# copie aquí el contenido de este proyecto (addons/, deploy/, Dockerfile, render.yaml, README.md)
git add .
git commit -m "Campus PI: módulo Odoo 17 con agentes IA"
git push origin main
```

### Paso 4 · Crear el servicio en Render
1. Entre a <https://dashboard.render.com> con GitHub → **New** → **Blueprint**.
2. Seleccione el repositorio `innovatechlab-politecnico`. Render detecta `render.yaml`.
3. Complete las variables:
   - `DATABASE_URL` = la cadena directa de Neon (paso 1)
   - `ANTHROPIC_API_KEY` = la clave del paso 2
4. Haga clic en **Apply**. El primer build tarda 5–10 min. El **primer arranque** inicializa la base de datos en Neon y puede tardar otros 5–15 min con el plan gratuito (0.1 CPU). Siga el progreso en **Logs** hasta ver `Registry loaded`.

### Paso 5 · Verificar
1. Abra `https://<su-servicio>.onrender.com/campus/login`.
2. Pruebe cada rol con los usuarios de la tabla.
3. Como administrador vaya a **Crear curso con IA**, suba un syllabus y revise el curso generado.
4. Como estudiante: Mis cursos → lección → marcar como completada → simulador → tutor IA.

### Paso 6 · Asegurar
- Cambie las contraseñas de prueba en **Configurar (Odoo) → Ajustes → Usuarios**.
- `ODOO_MASTER_PASSWORD` y `ODOO_ADMIN_PASSWORD` las genera Render y quedan en *Environment*.
- Si cambia el código, haga `git push`: Render redespliega y, con `ODOO_UPDATE=1`, actualiza el módulo.

---

## 3. Instalar en el Odoo 17 de su PC (sin Docker)
1. Copie `addons/campus_pi` dentro de una carpeta incluida en `addons_path` de su `odoo.conf`.
2. Reinicie Odoo con `-u base` o desde **Aplicaciones → Actualizar lista de aplicaciones**.
3. Busque **InnovaTech Lab · Campus PI** e instálelo. Para el idioma: **Ajustes → Idiomas → Español (CO)**.
4. Abra `http://localhost:8069/campus/login`.
5. Opcional: defina la variable de entorno `ANTHROPIC_API_KEY` antes de arrancar Odoo, o póngala en **Campus PI → IA → Configuración**.

Con Docker Desktop: `docker compose up --build` y abra `http://localhost:8069/campus/login`.

---

## 4. Críticas técnicas (léalas antes del piloto)

1. **Render gratis no sirve para clases reales.** Tiene 512 MB de RAM y 0.1 CPU, y el servicio se apaga tras 15 min sin tráfico (el siguiente ingreso tarda ~1 min o más con Odoo). Sirve para demo. Para un piloto con estudiantes use el plan **Starter**.
2. **Sin disco persistente en Render free.** Por eso el módulo guarda los adjuntos **dentro de PostgreSQL** (`ir_attachment.location = db`). Neon free tiene 0.5 GB: **no suba videos**. Use YouTube (no listado) o Drive y pegue la URL en la lección.
3. **Las sesiones se pierden** cuando Render reinicia el servicio. Los usuarios simplemente vuelven a iniciar sesión.
4. **Costo de IA.** Generar un curso consume decenas de miles de tokens, y cada respuesta del tutor, unos miles. Fije límites de gasto en la consola de Anthropic.
5. **Datos de certificaciones.** AI-901 se verificó en Microsoft Learn (puntaje 700, dominios 40-45 % / 55-60 %). Oracle 1Z0-830 y OpenEDG JSE-40-01 quedaron marcados como **POR VERIFICAR**: sus páginas oficiales no se pudieron consultar. Revíselos antes de cada cohorte.
6. **Las microcredenciales son institucionales.** No reemplazan el examen oficial del proveedor; el PDF lo dice explícitamente.
7. **Contenido pendiente.** Infografías, presentaciones y videos de los núcleos quedaron como lecciones con resumen. Los archivos institucionales (PPTX/PDF/MP4) se deben subir o enlazar desde **Editar en Odoo**.
8. **Protección de datos (Ley 1581 de 2012).** Las conversaciones con el tutor IA se envían a un proveedor externo (Anthropic). Informe a los estudiantes y actualice la política de tratamiento de datos.

## 5. Estructura
```
addons/campus_pi/        módulo Odoo 17
  models/                cursos, certificaciones, simulador, tutorías, agentes IA
  controllers/main.py    login, dashboards, aula, simulador, tutorías, admin
  views/                 backend Odoo + plantillas QWeb del campus
  data/                  usuarios, certificaciones, 3 cursos, banco de preguntas
  tools/gift.py          importador GIFT (Moodle)
deploy/start.sh          arranque en Render con DATABASE_URL
Dockerfile, render.yaml, docker-compose.yml
docs/                    investigación de certificaciones y propuesta de valor
```
