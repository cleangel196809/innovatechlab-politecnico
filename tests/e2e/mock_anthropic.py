# Servidor de prueba que imita la API de mensajes de Anthropic (incluida la búsqueda web).
# Uso: python3 mock_anthropic.py 9911   ->  CAMPUS_ANTHROPIC_URL=http://127.0.0.1:9911/v1/messages
import json
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CALLS = []
MODE = {"strict_models": True, "gemini_404_model": None, "fail_research": False, "fail_nucleo": None, "bad_json_once": set(), "pause_done": set()}


def text_block(t, citations=None):
    b = {"type": "text", "text": t}
    if citations:
        b["citations"] = citations
    return b


def research(payload):
    first = json.dumps(payload["messages"][0]["content"])[:50]
    if first not in MODE["pause_done"]:  # 1.ª llamada: simula pause_turn tras una búsqueda
        MODE["pause_done"].add(first)
        return {"stop_reason": "pause_turn", "content": [
            {"type": "server_tool_use", "id": "srv_1", "name": "web_search", "input": {"query": "CompTIA Security+ V8"}},
            {"type": "web_search_tool_result", "tool_use_id": "srv_1", "content": [
                {"type": "web_search_result", "url": "https://www.comptia.org/en-us/certifications/security/v8/", "title": "Security+ V8"},
                {"type": "web_search_result", "url": "https://www.nist.gov/cyberframework", "title": "NIST CSF"}]}]}
    data = {
        "certificacion": {"proveedor": "CompTIA", "nombre": "CompTIA Security+ V8", "codigo": "SY0-801",
                          "version": "V8", "estado": "Lanzamiento ~17-nov-2026", "url": "https://www.comptia.org/en-us/certifications/security/v8/",
                          "preguntas": 90, "duracion_min": 90, "puntaje_aprobacion": "750 / 900", "precio": "Según país",
                          "idiomas": "Inglés", "dominios": [{"nombre": "Conceptos generales de seguridad", "peso": 16}],
                          "notas": "Incluye riesgos de IA."},
        "nucleos": [{"numero": i, "novedades": ["Novedad 2026 del núcleo %d" % i], "conceptos_clave": ["Concepto A", "Concepto B"],
                     "recursos": [{"titulo": "Recurso oficial %d" % i, "url": "https://example.org/recurso-%d" % i, "tipo": "documentación"}]}
                    for i in range(1, 7)],
        "bibliografia": ["NIST. (2024). CSF 2.0."],
        "advertencias": ["El precio del voucher varía por país."],
    }
    txt = json.dumps(data, ensure_ascii=False)
    half = len(txt) // 2  # el JSON llega partido en dos bloques, como ocurre con las citas
    return {"stop_reason": "end_turn", "content": [
        {"type": "web_search_tool_result", "tool_use_id": "srv_2", "content": [
            {"type": "web_search_result", "url": "https://www.isc2.org/certifications/cc", "title": "ISC2 CC"}]},
        text_block("```json\n" + txt[:half], [{"type": "web_search_result_location", "url": "https://www.comptia.org/en-us/certifications/security/v8/", "title": "Security+ V8", "cited_text": "x"}]),
        text_block(txt[half:] + "\n```")]}


def nucleo(payload):
    prompt = payload["messages"][0]["content"]
    _log_material(prompt, "nucleo")
    num = int(re.search(r"NÚCLEO (\d+)", prompt).group(1))
    if MODE["fail_nucleo"] == num:
        return None
    key = "n%d" % num
    if num == 2 and key not in MODE["bad_json_once"]:  # 1.ª respuesta inválida -> el agente reintenta
        MODE["bad_json_once"].add(key)
        return {"stop_reason": "max_tokens", "content": [text_block('{"lectura": {"titulo": "cortado')]}
    doms = re.findall(r"Dominios: (.+)", prompt)
    dom = (doms[0].split(";")[0].rsplit(" ", 1)[0].strip()) if doms else "General"
    q = lambda k: {"domain": dom, "question": "Pregunta %d.%d sobre el núcleo: ¿cuál opción es correcta?" % (num, k),
                   "explanation": "Explicación %d.%d" % (num, k),
                   "options": [{"text": "Correcta %d" % k, "correct": True, "feedback": "Bien"},
                               {"text": "Incorrecta A", "correct": False, "feedback": "No"},
                               {"text": "Incorrecta B", "correct": False, "feedback": "No"},
                               {"text": "Incorrecta C", "correct": False, "feedback": "No"}]}
    data = {
        "lectura": {"titulo": "Lectura IA núcleo %d" % num, "resumen": "Resumen %d" % num,
                    "presentacion": "Presentación del núcleo %d.\n\nSegundo párrafo." % num,
                    "logros": ["Distinguir tipos de error", "Manejar excepciones"],
                    "secciones_html": "<h3>1. Introducción</h3><p>" + ("Contenido investigado del núcleo %d. " % num) * 60 +
                                      "</p><table class='table'><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
                                      "<pre><code>public class X {}</code></pre><p class='caption'>Código 1. Ejemplo.</p>"
                                      "<div class='cp-callout'><b>Regla</b><p>No tragues excepciones.</p></div>",
                    "buenas_practicas": ["Práctica 1", "Práctica 2"], "casos": [{"titulo": "El catch vacío", "texto": "¿Qué harías?"}],
                    "glosario": [{"termino": "Excepción", "significado": "Objeto que…"}],
                    "referencias": ["Oracle. (s. f.). Lesson: Exceptions. https://docs.oracle.com/javase/tutorial/essential/exceptions/"]},
        "bibliografia": {"principal": [{"titulo": "Introduction to Programming Using Java", "autor": "David J. Eck",
                                        "url": "https://math.hws.edu/javanotes/", "tema": "Excepciones", "paginas": "Cap. 8",
                                        "referencia": "Eck, D. J. (2022)."}],
                         "complementaria": [{"titulo": "Logging cheat sheet", "autor": "OWASP", "url": "https://cheatsheetseries.owasp.org/", "referencia": "OWASP (s. f.)"}]},
        "caso": ({"titulo": "MiPyme API – Parte %d" % num, "tiempo_horas": 12, "peso": "25 %", "contexto": "Camila administra El Surtidor.",
                  "indicaciones": ["Crear el proyecto", "Validar datos"], "entregables": ["Repositorio"],
                  "solucion": [{"escenario": "Producto válido", "accion": "POST /productos", "resultado": "201"}],
                  "rubrica": [{"criterio": "Excepciones", "bueno": "Completo", "regular": "Parcial", "insuficiente": "No", "puntaje": 2.5},
                              {"criterio": "Logs", "bueno": "Completo", "regular": "Parcial", "insuficiente": "No", "puntaje": 2.5}]}
                 if num == 3 else None),
        "presentacion": {"slides": [{"title": "Diapositiva %d" % k, "lead": "Idea %d" % k, "points": ["Punto 1", "Punto 2", "Punto 3"]} for k in range(1, 9)]},
        "infografia": {"titulo": "Infografía IA %d" % num, "pregunta_orientadora": "¿Pregunta %d?" % num, "dato_clave": "Dato clave %d" % num,
                       "texto_orientador": "Texto orientador", "terminos": [{"termino": "Término %d" % k, "texto": "Texto del término %d" % k,
                                                                           "icono": ["alerta", "codigo", "datos"][k % 3], "etiqueta": "Etiqueta %d" % k} for k in range(1, 11)]},
        "video": {"titulo": "Video IA %d" % num, "resumen": "Video corto", "guion_html": "<p>Guion del video %d</p>", "busqueda_youtube": "tema %d en español" % num},
        "actividad": {"titulo": "Actividad IA %d" % num, "resumen": "Actividad", "html": "<p>Instrucciones de la actividad %d</p>" % num},
        "laboratorio": ({"titulo": "Laboratorio IA %d" % num, "resumen": "Lab", "html": "<ol><li>Paso 1</li></ol>",
                         "recurso_url": "https://example.org/lab"} if num != 1 else None),
        "evaluacion": {"titulo": "Evaluación IA %d" % num, "resumen": "Evaluación", "html": "<table class='table'><tr><td>BUENO</td></tr></table>"},
        "sesion_virtual": {"resumen": "Sesión virtual IA", "agenda_html": "<ol><li>Agenda</li></ol>"},
        "sesion_presencial": {"resumen": "Sesión presencial IA", "guion_ia_html": "<ol><li>Guion</li></ol>"},
        "preguntas": [q(k) for k in range(1, 7)] + [{"domain": dom, "question": "Inválida sin correcta",
                                                     "options": [{"text": "a", "correct": False}, {"text": "b", "correct": False}]}],
    }
    return {"stop_reason": "end_turn", "content": [text_block(json.dumps(data, ensure_ascii=False))]}


def _log_material(prompt, kind):
    if "MATERIAL DEL DOCENTE" in prompt:
        num = re.search(r"NÚCLEO (\d+)", prompt).group(1)
        frag = prompt.split("MATERIAL DEL DOCENTE", 1)[1][:400].replace("\n", " ")
        with open("/tmp/mock_material.log", "a") as f:
            f.write("%s N%s: %s\n" % (kind, num, frag))


def media(payload):
    prompt = payload["messages"][0]["content"]
    _log_material(prompt, "media")
    num = int(re.search(r"NÚCLEO (\d+)", prompt).group(1))
    lays = ["portada", "puntos", "codigo", "tabla", "proceso", "comparacion", "cita", "cierre"]
    esc = []
    for k, lay in enumerate(lays):
        esc.append({"layout": lay, "title": "Escena %d.%d" % (num, k + 1), "subtitle": "", "icon": "alerta",
                    "points": ["Idea uno", "Idea dos", "Idea tres", "Idea cuatro"],
                    "code": "public class A {\n  void b() {}\n}" if lay == "codigo" else "",
                    "table": {"headers": ["Situación", "Código"], "rows": [["Inválido", "400"], ["No existe", "404"]]} if lay == "tabla" else {},
                    "narration": "Fíjate en esto. Esta es la narración natural de la escena %d del núcleo %d." % (k + 1, num)})
    act = {"titulo": "Actividad interactiva N%d" % num, "objetivo": "Validar", "instruccion": "Responde",
           "preguntas": [{"escena": k + 2, "enunciado": "Caso %d: ¿qué haces?" % k,
                          "opciones": [{"texto": "Correcta", "correcta": True, "retro": "¡Correcto! porque…"},
                                       {"texto": "Mala A", "correcta": False, "retro": "Incorrecto A"},
                                       {"texto": "Mala B", "correcta": False, "retro": "Incorrecto B"},
                                       {"texto": "Mala C", "correcta": False, "retro": "Incorrecto C"}]} for k in range(1, 6)]}
    data = {"escenas": esc, "busqueda_youtube": "tema %d" % num, "actividad": act}
    return {"stop_reason": "end_turn", "content": [text_block(json.dumps(data, ensure_ascii=False))]}


def bank(payload):
    prompt = payload["messages"][0]["content"]
    n = int(re.search(r"Genera (\d+) preguntas", prompt).group(1))
    doms = re.findall(r"([^:,]+): \d+", prompt.split("por dominio:")[1].split(". Preguntas")[0])
    qs = []
    for i in range(n):
        d = doms[i % len(doms)].strip()
        qs.append({"domain": d, "question": "Pregunta de banco %d (%s)" % (i, d), "explanation": "Exp",
                   "options": [{"text": "Sí", "correct": True, "feedback": "ok"}, {"text": "No", "correct": False, "feedback": "no"},
                               {"text": "Tal vez", "correct": False, "feedback": "no"}, {"text": "Nunca", "correct": False, "feedback": "no"}]})
    return {"stop_reason": "end_turn", "content": [text_block(json.dumps(qs, ensure_ascii=False))]}


VALID_CLAUDE = ["claude-fable-5-2", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/v1/models"):
            CALLS.append("list-models")
            return self._send(200, {"data": [{"id": i, "type": "model"} for i in VALID_CLAUDE]})
        return self._send(404, {})

    def do_POST(self):
        if self.path.startswith("/control"):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            MODE.update({k: (set(v) if isinstance(MODE.get(k), set) else v) for k, v in body.items()})
            return self._send(200, {"ok": True, "calls": CALLS[-50:]})
        raw = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        fmt = "gemini" if ":generateContent" in self.path else "openai" if self.path.endswith("/chat/completions") else "anthropic"
        if fmt == "gemini":
            if not self.headers.get("x-goog-api-key", "").startswith("AIza"):
                return self._send(400, {"error": {"code": 400, "message": "API key not valid"}})
            if MODE.get("gemini_404_model") and MODE["gemini_404_model"] in self.path:
                return self._send(404, {"error": {"code": 404, "message": "model not found"}})
            payload = {"system": raw["systemInstruction"]["parts"][0]["text"],
                       "messages": [{"role": "assistant" if c["role"] == "model" else "user",
                                     "content": c["parts"][0]["text"]} for c in raw["contents"]],
                       "tools": raw.get("tools"), "model": self.path.split("/models/")[1].split(":")[0]}
            CALLS.append("gemini:" + payload["model"])
        elif fmt == "openai":
            if not self.headers.get("Authorization", "").startswith("Bearer gsk_"):
                return self._send(401, {"error": {"message": "Invalid API Key"}})
            payload = {"system": raw["messages"][0]["content"], "messages": raw["messages"][1:], "tools": None,
                       "model": raw["model"]}
            CALLS.append("openai:" + raw["model"] + (":json" if raw.get("response_format") else ""))
        else:
            payload = raw
            if not self.headers.get("x-api-key", "").startswith("sk-ant-"):
                return self._send(401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}})
            if MODE.get("strict_models") and raw.get("model") not in VALID_CLAUDE:
                return self._send(404, {"type": "error", "error": {"type": "not_found_error", "message": "model: %s" % raw.get("model")}})
            if "temperature" in raw and raw.get("model") in VALID_CLAUDE:
                CALLS.append("rejected-temperature")
                return self._send(400, {"type": "error", "error": {"type": "invalid_request_error", "message": "`temperature` is deprecated for this model."}})
        self._fmt = fmt
        system = payload.get("system") or ""
        prompt = json.dumps(payload["messages"][0]["content"], ensure_ascii=False)
        kind = ("structure" if "Extraes la estructura" in system else "research" if (payload.get("tools") or "Agente Investigador" in system) else "bank" if "Genera " in prompt and "por dominio" in prompt
                else "nucleo" if "UN núcleo" in system else "media" if "guionista" in system else "chat")
        CALLS.append(kind)
        time.sleep(0.3)
        if MODE.get("fail_research") and kind == "research":
            return self._send(500, {"type": "error", "error": {"type": "api_error", "message": "Internal"}})
        if kind == "structure":
            st = {"asignatura": "Syllabus desde texto", "nucleos": [
                {"numero": i, "titulo": "Núcleo IA %d desde PDF" % i, "temas": ["Tema %d.1" % i, "Tema %d.2" % i],
                 "objetivo": "Objetivo %d" % i, "estrategias": ["Trabajo autónomo."], "criterios": ["Criterio %d" % i]} for i in range(1, 5)],
                "evaluacion": [{"cuando": "Al finalizar el Núcleo 3", "instrumento": "Proyecto con rúbrica", "evidencia": "Proyecto"}]}
            res = {"stop_reason": "end_turn", "content": [text_block(json.dumps(st, ensure_ascii=False))]}
        elif kind == "research":
            res = research(payload)
        elif kind == "nucleo":
            res = nucleo(payload)
            if res is None:
                return self._send(529, {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}})
        elif kind == "media":
            res = media(payload)
        elif kind == "bank":
            res = bank(payload)
        else:
            last = payload["messages"][-1]["content"]
            res = {"stop_reason": "end_turn", "content": [text_block("Respuesta (%s) sobre: %s" % (
                "docente" if "Asistente IA del" in system else "estudiante", last[:200]))]}
        if fmt == "anthropic":
            res.update({"id": "msg_mock", "type": "message", "role": "assistant", "model": payload.get("model")})
            return self._send(200, res)
        text = "".join(b.get("text", "") for b in res["content"] if b.get("type") == "text")
        if res.get("stop_reason") == "pause_turn":  # otros proveedores no pausan: devolver el resultado final
            res = research(payload)
            text = "".join(b.get("text", "") for b in res["content"] if b.get("type") == "text")
        text = text.replace("```json", "").replace("```", "")
        if fmt == "gemini":
            cand = {"content": {"role": "model", "parts": [{"text": text}]},
                    "finishReason": "MAX_TOKENS" if res.get("stop_reason") == "max_tokens" else "STOP"}
            if payload.get("tools"):
                cand["groundingMetadata"] = {"groundingChunks": [{"web": {"uri": "https://www.comptia.org/en-us/certifications/security/v8/", "title": "comptia.org"}}]}
            return self._send(200, {"candidates": [cand]})
        return self._send(200, {"choices": [{"message": {"role": "assistant", "content": text},
                                             "finish_reason": "length" if res.get("stop_reason") == "max_tokens" else "stop"}]})

    def _send(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 9911), H).serve_forever()
