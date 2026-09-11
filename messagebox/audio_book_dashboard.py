"""Small dashboard adapter for the personal Audio Book section."""

import json
import time
import urllib.parse
from pathlib import Path

from messagebox.audio_books import BookError, BookLibrary, BookRuntime
from messagebox.nfc_state import NfcError
from messagebox.runtime_paths import NFC_HEALTH_FILE


def get_books(handler, *, library=None, runtime=None):
    try:
        state = (library or BookLibrary()).public()
        state.update((runtime or BookRuntime()).public())
        try:
            state["reader_ready"] = 0 <= time.time() - Path(NFC_HEALTH_FILE).stat().st_mtime < 5
        except OSError:
            state["reader_ready"] = False
        return handler._send(200, json.dumps(state))
    except (OSError, ValueError):
        return handler._send(503, json.dumps({"error": "The library is unavailable. Please try again."}))


def post_books(handler, path, *, library=None, runtime=None):
    library, runtime = library or BookLibrary(), runtime or BookRuntime()
    try:
        if path == "/api/audio-books/upload":
            if handler.headers.get("Transfer-Encoding"):
                raise BookError("The upload must include the file size.")
            if handler.headers.get("Content-Type") != "application/octet-stream":
                raise BookError("Unsupported upload format.")
            try:
                length = int(handler.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise BookError("Invalid file size.") from exc
            filename = urllib.parse.unquote(handler.headers.get("X-Audio-Filename", ""))
            if len(filename) > 512:
                raise BookError("The file name is too long.")
            connection = getattr(handler, "connection", None)
            previous_timeout = connection.gettimeout() if connection is not None else None
            try:
                if connection is not None:
                    connection.settimeout(60)
                key = library.upload(handler.rfile, length, filename)
            finally:
                if connection is not None:
                    connection.settimeout(previous_timeout)
            return handler._send(201, json.dumps({"ok": True, "id": key}))
        payload = handler._json_body(limit=2048)
        if payload is None:
            return
        action, key = payload.get("action"), payload.get("id")
        if action == "pair":
            library.path_for(key)
            try:
                ready = 0 <= time.time() - Path(NFC_HEALTH_FILE).stat().st_mtime < 5
            except OSError:
                ready = False
            if not ready:
                raise BookError("The NFC reader is unavailable. Check its connection and service.")
            runtime.begin_pair(key)
        elif action == "cancel_pair":
            runtime.cancel_pair()
        elif action in {"rename", "unpair", "delete"}:
            if action == "delete" and runtime.public()["player"].get("book") == key:
                raise BookError("This book is playing. Wait until it finishes before deleting it.")
            library.change(key, action, payload.get("title"))
        else:
            raise BookError("Unknown action.")
        return handler._send(200, '{"ok":true}')
    except BookError as exc:
        return handler._send(400, json.dumps({"error": str(exc)}))
    except (NfcError, OSError, ValueError, TypeError):
        return handler._send(503, json.dumps({"error": "The operation failed. Check the microSD and try again."}))
