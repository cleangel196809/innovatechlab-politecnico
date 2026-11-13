# -*- coding: utf-8 -*-
"""Capa común para varios proveedores de IA (sin dependencias de Odoo, apta para hilos).

Proveedores
- anthropic : Claude (API de mensajes; búsqueda web del servidor ``web_search``).
- gemini    : Google Gemini (generateContent; búsqueda con ``google_search`` cuando el modelo/plan lo permite).
              Tiene nivel gratuito: clave en https://aistudio.google.com/apikey
- groq      : API compatible con OpenAI, nivel gratuito (https://console.groq.com/keys). Sin búsqueda web.
- openai    : ChatGPT por API (de pago). Sin búsqueda web en esta integración.
- compatible: cualquier API compatible con OpenAI (OpenRouter, Ollama, LM Studio…) con URL y modelo propios.

``call(conf, system, messages, max_tokens, temperature, web_search, json_mode, timeout)``
devuelve ``(texto, fuentes, stop)`` donde stop ∈ {"end", "max_tokens", ...}.
"""
import json
import logging
import time

import requests

_logger = logging.getLogger(__name__)

PROVIDERS = {
    "anthropic": {"label": "Claude (Anthropic)", "url": "https://api.anthropic.com/v1/messages",
                  "model": "claude-sonnet-5-5", "fallback": None, "search": True, "parallel": 4, "max_out": 16000},
    "gemini": {"label": "Gemini (Google)", "url": "https://generativelanguage.googleapis.com/v1beta",
               "model": "gemini-flash-latest", "fallback": "gemini-flash-lite-latest", "search": True,
               "parallel": 1, "max_out": 16000},
    "groq": {"label": "Groq (Llama, gratuito)", "url": "https://api.groq.com/openai/v1",
             "model": "llama-3.3-70b-versatile", "fallback": "llama-3.1-8b-instant", "search": False,
             "parallel": 1, "max_out": 7000},
    "openai": {"label": "ChatGPT (OpenAI)", "url": "https://api.openai.com/v1",
               "model": "gpt-4o-mini", "fallback": None, "search": False, "parallel": 2, "max_out": 12000},
    "compatible": {"label": "Compatible con OpenAI", "url": "", "model": "", "fallback": None, "search": False,
                   "parallel": 1, "max_out": 8000},
}


class LLMError(Exception):
    pass


# Modelos resueltos automáticamente cuando el configurado ya no existe (p. ej., retirado)
RESOLVED = {}


def _is_model_missing(resp):
    return resp is not None and resp.status_code == 404 and "model" in (resp.text or "").lower()


def _pick(ids, prefer):
    for want in prefer:
        for i in ids:
            if want in i:
                return i
    return ids[0] if ids else None


def resolve_anthropic_model(conf, current):
    """Consulta /v1/models y elige el Sonnet más reciente disponible para la cuenta."""
    url = (conf.get("url") or PROVIDERS["anthropic"]["url"]).replace("/messages", "/models")
    try:
        resp = requests.get(url, headers={"x-api-key": conf["key"], "anthropic-version": "2023-06-01"},
                            params={"limit": 100}, timeout=30)
        ids = [m["id"] for m in resp.json().get("data", []) if m.get("id")] if resp.status_code < 400 else []
    except (requests.RequestException, ValueError):
        ids = []
    family = "haiku" if "haiku" in (current or "") else "opus" if "opus" in (current or "") else "sonnet"
    return _pick(ids, [family, "sonnet", "haiku"])


def resolve_gemini_model(conf, current):
    base = (conf.get("url") or PROVIDERS["gemini"]["url"]).rstrip("/")
    try:
        resp = requests.get(base + "/models", headers={"x-goog-api-key": conf["key"]}, params={"pageSize": 200},
                            timeout=30)
        ids = [m["name"].split("/", 1)[-1] for m in resp.json().get("models", [])
               if "generateContent" in (m.get("supportedGenerationMethods") or [])] if resp.status_code < 400 else []
    except (requests.RequestException, ValueError):
        ids = []
    ids = [i for i in ids if "flash" in i and not any(x in i for x in ("image", "tts", "audio", "live", "embedding"))]
    return _pick(ids, ["flash-latest", "flash-lite-latest", "flash"])


def label(conf):
    p = PROVIDERS.get(conf.get("provider") or "", {})
    return "%s · %s" % (p.get("label", conf.get("provider")), conf.get("model") or p.get("model"))


def _post(url, payload, headers, timeout, tries=4):
    """POST con reintentos ante 429/5xx (límites de los niveles gratuitos)."""
    last = None
    for attempt in range(tries):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            last = LLMError("No fue posible contactar al proveedor de IA: %s" % e)
            time.sleep(2 * (attempt + 1))
            continue
        if resp.status_code in (429, 500, 502, 503, 529) and attempt < tries - 1:
            wait = resp.headers.get("retry-after")
            try:
                wait = min(float(wait), 40.0)
            except (TypeError, ValueError):
                wait = 5.0 * (attempt + 1)
            _logger.warning("IA %s: %s, reintento en %ss", url.split("?")[0], resp.status_code, wait)
            time.sleep(wait)
            last = resp
            continue
        return resp
    if isinstance(last, LLMError):
        raise last
    return last


SAMPLING = ("temperature", "top_p", "top_k")
NO_SAMPLING = set()  # (proveedor, modelo) que rechazan parámetros de muestreo


def _rejected_param(resp, payload):
    """Si el proveedor rechaza un parámetro (p. ej. 'temperature is deprecated'), devuelve su nombre."""
    if resp is None or resp.status_code != 400:
        return None
    txt = (resp.text or "").lower()
    for k in SAMPLING:
        if k in payload and k in txt:
            return k
    return None


def _err(resp):
    return LLMError("Error del proveedor de IA (%s): %s" % (resp.status_code, resp.text[:300]))


def _alternate(messages):
    """Une mensajes consecutivos del mismo rol (Gemini exige alternancia user/model)."""
    out = []
    for m in messages:
        content = m["content"] if isinstance(m["content"], str) else json.dumps(m["content"], ensure_ascii=False)
        if out and out[-1]["role"] == m["role"]:
            out[-1]["content"] += "\n\n" + content
        else:
            out.append({"role": m["role"], "content": content})
    if out and out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": "(inicio de la conversación)"})
    return out


# ------------------------------------------------------------------ Anthropic
def _modern_claude(model):
    """Modelos Claude de generación 5 en adelante: no admiten 'temperature'."""
    import re
    m = re.search(r"claude-(?:[a-z]+-)?(\d+)", model or "")
    return bool(m and int(m.group(1)) >= 5)


def _anthropic(conf, system, messages, max_tokens, temperature, web_search, json_mode, timeout):
    p = PROVIDERS["anthropic"]
    wanted = conf.get("model") or p["model"]
    model = RESOLVED.get(("anthropic", wanted), wanted)
    payload = {"model": model, "max_tokens": max_tokens, "system": system,
               "messages": list(messages)}
    if web_search:
        payload["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}]
    elif temperature is not None and ("anthropic", model) not in NO_SAMPLING and not _modern_claude(model):
        payload["temperature"] = temperature
    headers = {"x-api-key": conf["key"], "anthropic-version": "2023-06-01", "content-type": "application/json"}
    texts, sources, stop = [], [], None
    for _turn in range(5):
        resp = _post(conf.get("url") or p["url"], payload, headers, timeout)
        if _is_model_missing(resp):
            alt = resolve_anthropic_model(conf, payload["model"])
            if alt and alt != payload["model"]:
                _logger.warning("Modelo %s no disponible; se usa %s", payload["model"], alt)
                RESOLVED[("anthropic", wanted)] = alt
                conf["resolved_model"] = alt
                payload["model"] = alt
                if _modern_claude(alt):
                    payload.pop("temperature", None)
                resp = _post(conf.get("url") or p["url"], payload, headers, timeout)
        bad = _rejected_param(resp, payload)
        while bad:
            _logger.warning("El modelo %s rechaza '%s'; se reintenta sin él", payload["model"], bad)
            NO_SAMPLING.add(("anthropic", payload["model"]))
            for k in SAMPLING:
                payload.pop(k, None)
            resp = _post(conf.get("url") or p["url"], payload, headers, timeout)
            bad = _rejected_param(resp, payload)
        if (resp.status_code == 400 and "tools" in payload
                and any(w in (resp.text or "").lower() for w in ("web_search", "tool"))):
            _logger.warning("Búsqueda web no disponible para %s; se continúa sin ella", payload["model"])
            payload.pop("tools")
            resp = _post(conf.get("url") or p["url"], payload, headers, timeout)
        if resp.status_code >= 400:
            raise _err(resp)
        data = resp.json()
        stop = data.get("stop_reason")
        for b in data.get("content", []):
            if b.get("type") == "text":
                texts.append(b.get("text", ""))
                for c in b.get("citations") or []:
                    if c.get("url"):
                        sources.append({"title": c.get("title") or c["url"], "url": c["url"]})
            elif b.get("type") == "web_search_tool_result" and isinstance(b.get("content"), list):
                for r in b["content"]:
                    if r.get("url"):
                        sources.append({"title": r.get("title") or r["url"], "url": r["url"]})
        if stop != "pause_turn":
            break
        payload["messages"] = payload["messages"] + [{"role": "assistant", "content": data.get("content", [])}]
    return "".join(texts), sources, ("max_tokens" if stop == "max_tokens" else "end")


# --------------------------------------------------------------------- Gemini
def _gemini(conf, system, messages, max_tokens, temperature, web_search, json_mode, timeout):
    p = PROVIDERS["gemini"]
    base = (conf.get("url") or p["url"]).rstrip("/")
    wanted = conf.get("model") or p["model"]
    models = [m for m in [RESOLVED.get(("gemini", wanted), wanted), p["fallback"]] if m]
    contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                for m in _alternate(messages)]
    gen = {"maxOutputTokens": max_tokens, "temperature": temperature}
    if json_mode and not web_search:
        gen["responseMimeType"] = "application/json"
    payload = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents, "generationConfig": gen}
    if web_search:
        payload["tools"] = [{"google_search": {}}]
    headers = {"x-goog-api-key": conf["key"], "content-type": "application/json"}
    resp = None
    for model in models:
        resp = _post("%s/models/%s:generateContent" % (base, model), payload, headers, timeout)
        if resp.status_code == 400 and web_search and "tools" in payload:
            # El plan o el modelo no admite búsqueda: se repite sin ella
            payload.pop("tools")
            resp = _post("%s/models/%s:generateContent" % (base, model), payload, headers, timeout)
        if resp.status_code in (404, 429) and model != models[-1]:
            continue
        break
    if _is_model_missing(resp):
        alt = resolve_gemini_model(conf, wanted)
        if alt:
            RESOLVED[("gemini", wanted)] = alt
            conf["resolved_model"] = alt
            resp = _post("%s/models/%s:generateContent" % (base, alt), payload, headers, timeout)
    if resp.status_code >= 400:
        raise _err(resp)
    data = resp.json()
    cands = data.get("candidates") or []
    if not cands:
        raise LLMError("Gemini no devolvió respuesta (%s)" % json.dumps(data.get("promptFeedback") or data)[:200])
    c = cands[0]
    text = "".join(part.get("text", "") for part in (c.get("content") or {}).get("parts", []) if not part.get("thought"))
    sources = []
    for ch in (c.get("groundingMetadata") or {}).get("groundingChunks") or []:
        web = ch.get("web") or {}
        if web.get("uri"):
            sources.append({"title": web.get("title") or web["uri"], "url": web["uri"]})
    return text, sources, ("max_tokens" if c.get("finishReason") == "MAX_TOKENS" else "end")


# ----------------------------------------------------- OpenAI / Groq / otros
def _openai_like(conf, system, messages, max_tokens, temperature, web_search, json_mode, timeout):
    prov = conf.get("provider")
    p = PROVIDERS.get(prov, PROVIDERS["compatible"])
    base = (conf.get("url") or p["url"]).rstrip("/")
    if not base:
        raise LLMError("Configure la URL base del proveedor compatible con OpenAI.")
    models = [m for m in [conf.get("model") or p["model"], p["fallback"]] if m]
    if not models:
        raise LLMError("Configure el modelo del proveedor de IA.")
    msgs = [{"role": "system", "content": system}] + [
        {"role": m["role"], "content": m["content"]} for m in _alternate(messages)]
    headers = {"Authorization": "Bearer %s" % conf["key"], "content-type": "application/json"}
    resp = None
    for model in models:
        payload = {"model": model, "messages": msgs}
        if temperature is not None and (prov, model) not in NO_SAMPLING:
            payload["temperature"] = temperature
        payload["max_completion_tokens" if prov == "openai" else "max_tokens"] = min(max_tokens, p["max_out"])
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        resp = _post(base + "/chat/completions", payload, headers, timeout)
        if resp.status_code == 400 and json_mode and "response_format" in resp.text:
            payload.pop("response_format")
            resp = _post(base + "/chat/completions", payload, headers, timeout)
        if _rejected_param(resp, payload):
            NO_SAMPLING.add((prov, model))
            for k in SAMPLING:
                payload.pop(k, None)
            resp = _post(base + "/chat/completions", payload, headers, timeout)
        if resp.status_code in (404, 429) and model != models[-1]:
            continue
        break
    if resp.status_code >= 400:
        raise _err(resp)
    data = resp.json()
    choice = (data.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content") or ""
    return text, [], ("max_tokens" if choice.get("finish_reason") == "length" else "end")


def call(conf, system, messages, max_tokens=2000, temperature=0.4, web_search=False, json_mode=False, timeout=300):
    prov = conf.get("provider")
    if not prov or not conf.get("key"):
        raise LLMError("No hay un proveedor de IA configurado.")
    p = PROVIDERS.get(prov, PROVIDERS["compatible"])
    max_tokens = min(max_tokens, p["max_out"])
    if prov == "anthropic":
        return _anthropic(conf, system, messages, max_tokens, temperature, web_search, json_mode, timeout)
    if prov == "gemini":
        return _gemini(conf, system, messages, max_tokens, temperature, web_search, json_mode, timeout)
    return _openai_like(conf, system, messages, max_tokens, temperature, web_search, json_mode, timeout)
