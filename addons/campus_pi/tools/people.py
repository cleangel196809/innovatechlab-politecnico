# -*- coding: utf-8 -*-
"""Lectura de listados de estudiantes o docentes desde Excel (.xlsx) o CSV.

Columnas reconocidas (en cualquier orden, la fila de títulos puede estar en las primeras 10 filas):
    nombre | nombres | nombre completo | estudiante | docente
    correo | email | e-mail | correo institucional | usuario
    teléfono | celular | móvil                       (opcional)
    whatsapp                                         (opcional; se pide en cursos de inglés o informática)
Si no hay títulos reconocibles se asume el orden A = nombre, B = correo, C = WhatsApp.
"""
import csv
import io
import re
import unicodedata

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def _norm(t):
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", t)


_KEYS = {
    "name": ("nombre", "nombres", "nombrecompleto", "nombresyapellidos", "estudiante", "docente", "name", "apellidosynombres"),
    "email": ("correo", "email", "mail", "correoinstitucional", "correoelectronico", "usuario", "login"),
    "whatsapp": ("whatsapp", "numerodewhatsapp", "numerowhatsapp", "wa", "telefonowhatsapp", "celularwhatsapp"),
    "phone": ("telefono", "celular", "movil", "phone", "mobile", "numerocelular", "numerodetelefono", "tel"),
}


def _match(cell):
    n = _norm(cell)
    if not n:
        return None
    if "whatsapp" in n:
        return "whatsapp"
    for key, words in _KEYS.items():
        if n in words or any(n.startswith(w) for w in words if len(w) > 4):
            return key
    return None


def read_rows(data, filename=""):
    """Devuelve una lista de filas (listas de texto) del archivo."""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")) or data[:2] == b"PK":
        try:
            import openpyxl
        except ImportError as e:  # pragma: no cover
            raise ValueError("El servidor no tiene openpyxl para leer Excel; guarde el archivo como CSV.") from e
        try:
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as e:  # noqa: BLE001
            raise ValueError("No se pudo abrir el Excel (%s). Guárdelo de nuevo como .xlsx." % e) from e
        ws = wb.worksheets[0]
        rows = [["" if v is None else str(v).strip() for v in r] for r in ws.iter_rows(values_only=True)]
        wb.close()
        return rows
    if name.endswith(".xls"):
        raise ValueError("El formato .xls antiguo no es compatible: guarde el archivo como .xlsx o .csv.")
    text = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:2000]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    return [[c.strip() for c in r] for r in csv.reader(io.StringIO(text), delimiter=delim)]


def _phone(v):
    v = str(v or "").strip()
    if re.match(r"^\d+\.0$", v):  # Excel guarda números como float
        v = v[:-2]
    digits = re.sub(r"\D", "", v)
    if not digits:
        return ""
    if len(digits) == 10 and digits.startswith("3"):  # celular colombiano sin indicativo
        return "+57 " + digits
    if len(digits) == 12 and digits.startswith("573"):
        return "+57 " + digits[2:]
    return ("+" if v.strip().startswith("+") or len(digits) > 10 else "") + digits


def _guess_columns(rows):
    """Sin títulos: la columna con '@' es el correo, la más numérica el WhatsApp y la primera de texto el nombre."""
    sample = [r for r in rows if any(str(c).strip() for c in r)][:30]
    ncol = max((len(r) for r in sample), default=0)
    if not ncol:
        return {"name": 0, "email": 1, "phone": 2}

    def score(j, test):
        return sum(1 for r in sample if j < len(r) and test(str(r[j]).strip()))
    email = max(range(ncol), key=lambda j: score(j, lambda v: "@" in v))
    rest = [j for j in range(ncol) if j != email]
    phone = max(rest, key=lambda j: score(j, lambda v: len(re.sub(r"\D", "", v)) >= 7), default=None)
    if phone is not None and not score(phone, lambda v: len(re.sub(r"\D", "", v)) >= 7):
        phone = None
    names = [j for j in rest if j != phone]
    cols = {"email": email, "name": names[0] if names else (rest[0] if rest else 0)}
    if phone is not None:
        cols["phone"] = phone
        nums = [j for j in rest if j not in (phone,) and j not in names[:1]
                and score(j, lambda v: len(re.sub(r"\D", "", v)) >= 7)]
        if nums:
            cols["whatsapp"] = nums[0]
    return cols


def parse_people(data, filename=""):
    """Devuelve (personas, errores). personas = [{name, email, phone, row}]."""
    rows = [r for r in read_rows(data, filename)]
    cols, start = None, 0
    for i, r in enumerate(rows[:10]):
        found = {}
        for j, c in enumerate(r):
            k = _match(c)
            if k and k not in found:
                found[k] = j
        if "email" in found and "name" in found:
            cols, start = found, i + 1
            break
    if cols is None:
        cols = _guess_columns(rows)
    people, errors, seen = [], [], set()
    for i, r in enumerate(rows[start:], start + 1):
        get = lambda k: (r[cols[k]] if k in cols and cols[k] < len(r) else "") or ""  # noqa: E731
        name = re.sub(r"\s+", " ", get("name")).strip()
        email = get("email").strip().lower().replace("mailto:", "")
        if not name and not email:
            continue
        if not EMAIL_RE.match(email):
            errors.append({"row": i, "name": name, "email": email, "error": "Correo no válido"})
            continue
        if not name:
            errors.append({"row": i, "name": name, "email": email, "error": "Falta el nombre"})
            continue
        if email in seen:
            errors.append({"row": i, "name": name, "email": email, "error": "Correo repetido en el archivo"})
            continue
        seen.add(email)
        phone, wa = _phone(get("phone")), _phone(get("whatsapp"))
        people.append({"row": i, "name": name.title() if name.isupper() or name.islower() else name,
                       "email": email, "phone": phone, "whatsapp": wa})
    return people, errors


def template_xlsx(role="estudiantes"):
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = role.capitalize()
    ws.append(["Nombre completo", "Teléfono", "Correo", "WhatsApp (opcional)"])
    ws.append(["Ana María Pérez Gómez", "6015551234", "ana.perez@pi.edu.co", "3001234567"])
    ws.append(["Juan Camilo Rojas", "3109876543", "juan.rojas@pi.edu.co", ""])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="002060")
    for col, w in zip("ABCD", (36, 18, 34, 20)):
        ws.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def credentials_xlsx(results):
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Credenciales"
    ws.append(["Nombre", "Usuario (correo)", "Contraseña inicial", "Teléfono", "WhatsApp", "Rol", "Resultado"])
    for r in results:
        ws.append([r.get("name"), r.get("email"), r.get("password") or "(sin cambio)", r.get("phone"), r.get("whatsapp"),
                   r.get("role"), r.get("status")])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="002060")
    for col, w in zip("ABCDEFG", (34, 34, 20, 18, 18, 12, 44)):
        ws.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
