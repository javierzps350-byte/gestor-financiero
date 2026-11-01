"""Reconocimiento local de una sola intervención mediante Vosk.

Solo se activa cuando el usuario pulsa el botón de micrófono. Requiere instalar
requirements_voice.txt y descargar un modelo español en models/vosk-es.
"""
import json
import queue
from pathlib import Path

from src.config import MODEL_DIR

MODEL_PATH = MODEL_DIR / "vosk-es"


def is_voice_engine_available() -> bool:
    try:
        import sounddevice  # noqa: F401
        import vosk  # noqa: F401
        return MODEL_PATH.exists() and any(MODEL_PATH.iterdir())
    except (ImportError, OSError):
        return False


def listen_once(max_seconds: int = 18) -> str:
    try:
        import sounddevice as sd
        from vosk import KaldiRecognizer, Model
    except ImportError as exc:
        raise RuntimeError("Faltan los componentes opcionales. Instala installer/requirements_voice.txt.") from exc

    if not MODEL_PATH.exists() or not any(MODEL_PATH.iterdir()):
        raise RuntimeError(
            f"No se encontró el modelo de voz en {MODEL_PATH}. "
            "Descarga un modelo español de Vosk y colócalo en esa carpeta."
        )

    audio_queue: queue.Queue[bytes] = queue.Queue()
    model = Model(str(MODEL_PATH))
    recognizer = KaldiRecognizer(model, 16000)

    def callback(indata, _frames, _time, status):
        if status:
            return
        audio_queue.put(bytes(indata))

    pieces = []
    with sd.RawInputStream(
        samplerate=16000, blocksize=8000, dtype="int16", channels=1, callback=callback
    ):
        import time
        started = time.monotonic()
        while time.monotonic() - started < max_seconds:
            try:
                data = audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if recognizer.AcceptWaveform(data):
                text = json.loads(recognizer.Result()).get("text", "").strip()
                if text:
                    pieces.append(text)
        final = json.loads(recognizer.FinalResult()).get("text", "").strip()
        if final:
            pieces.append(final)
    return " ".join(pieces).strip()
