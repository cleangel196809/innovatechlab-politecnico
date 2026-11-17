# -*- coding: utf-8 -*-
"""Voz natural para la narración de presentaciones y videos.

Usa las voces neuronales de Microsoft (paquete libre ``edge-tts``, sin API key): suenan como una
persona y no como la voz robótica del navegador. Si el paquete no está instalado o el servicio no
responde, la aplicación cae a la voz del navegador (ver campus.js).
"""
import asyncio
import logging
import threading

_logger = logging.getLogger(__name__)

VOICES = [
    ("es-CO-GonzaloNeural", "Gonzalo · Colombia (masculina)"),
    ("es-CO-SalomeNeural", "Salomé · Colombia (femenina)"),
    ("es-MX-JorgeNeural", "Jorge · México (masculina)"),
    ("es-MX-DaliaNeural", "Dalia · México (femenina)"),
    ("es-US-AlonsoNeural", "Alonso · Latino EE. UU. (masculina)"),
    ("es-US-PalomaNeural", "Paloma · Latino EE. UU. (femenina)"),
    ("es-AR-TomasNeural", "Tomás · Argentina (masculina)"),
    ("es-ES-AlvaroNeural", "Álvaro · España (masculina)"),
    ("es-ES-ElviraNeural", "Elvira · España (femenina)"),
]
DEFAULT_VOICE = "es-CO-GonzaloNeural"
DEFAULT_RATE = "-4%"


def available():
    try:
        import edge_tts  # noqa: F401
        return True
    except ImportError:
        return False


async def _synth(text, voice, rate, pitch):
    import edge_tts
    com = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    chunks = []
    async for part in com.stream():
        if part.get("type") == "audio":
            chunks.append(part["data"])
    return b"".join(chunks)


def synthesize(text, voice=None, rate=None, pitch="+0Hz", timeout=60):
    """Devuelve el MP3 de ``text`` o lanza una excepción. Se ejecuta en un hilo propio para no
    chocar con un bucle asyncio existente."""
    voice = voice or DEFAULT_VOICE
    rate = rate or DEFAULT_RATE
    out, err = {}, {}

    def run():
        try:
            out["mp3"] = asyncio.run(asyncio.wait_for(_synth(text, voice, rate, pitch), timeout))
        except Exception as e:  # noqa: BLE001
            err["e"] = e

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout + 5)
    if err.get("e"):
        raise err["e"]
    if not out.get("mp3"):
        raise RuntimeError("El servicio de voz no devolvió audio")
    return out["mp3"]
