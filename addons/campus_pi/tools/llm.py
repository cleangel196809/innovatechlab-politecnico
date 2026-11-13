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
                  "model": "claude-sonnet-4-5", "fallback": None, "search": True, "parallel": 4, "max_out": 16000},
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
def _anthropic(conf, system, messages, max_tokens, temperature, web_search, json_mode, timeout):
    p = PROVIDERS["anthropic"]
    payload = {"model": conf.get("model") or p["model"], "max_tokens": max_tokens, "system": system,
               "messages": list(messages)}
    if web_search:
        payload["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}]
    else:
        payload["temperature"] = temperature
    headers = {"x-api-key": conf["key"], "anthropic-version": "2023-06-01", "content-type": "application/json"}
    texts, sources, stop = [], [], None
    for _turn in range(5):
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
    models = [m for m in [conf.get("model") or p["model"], p["fallback"]] if m]
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
        payload = {"model": model, "messages": msgs, "temperature": temperature}
        payload["max_completion_tokens" if prov == "openai" else "max_tokens"] = min(max_tokens, p["max_out"])
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        resp = _post(base + "/chat/completions", payload, headers, timeout)
        if resp.status_code == 400 and json_mode and "response_format" in resp.text:
            payload.pop("response_format")
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
