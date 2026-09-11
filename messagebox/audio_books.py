"""Personal Audio Book library. Durable media, transient scans, no bookmarks."""

import errno
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
import wave
from pathlib import Path

from messagebox.nfc_state import _atomic_json, _load_json, _locked_path, normalize_uid
from messagebox.runtime_paths import DATA_DIR, RUNTIME_DIR

LIBRARY_DIR = DATA_DIR / "audio-books"
BOOK_RUNTIME = RUNTIME_DIR / "audio-books.json"
MAX_UPLOAD_BYTES = 256 * 1024 * 1024
RESERVE_BYTES = 64 * 1024 * 1024
MAX_SECONDS = 3600
MAX_WAV_BYTES = (MAX_SECONDS + 2) * 48000 + 4096
FORMATS = {".mp3": "mp3", ".wav": "wav", ".ogg": "ogg", ".m4a": "mov", ".flac": "flac", ".aac": "aac"}


class BookError(ValueError):
    """Content-free error safe for the household dashboard."""


def book_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise BookError("Book not found.")
    return value


def title(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 120:
        raise BookError("The title must contain between 1 and 120 characters.")
    if any(ord(char) < 32 for char in value):
        raise BookError("The title contains an unsupported character.")
    return value.strip()


class BookLibrary:
    def __init__(self, root=LIBRARY_DIR):
        self.root = Path(root)
        self.path = self.root / "library.json"

    def load(self):
        data = _load_json(self.path, {"version": 1, "books": {}})
        if data.get("version") != 1 or not isinstance(data.get("books"), dict):
            raise BookError("The library could not be read.")
        cards = set()
        for key, entry in data["books"].items():
            book_id(key)
            if not isinstance(entry, dict):
                raise BookError("The library could not be read.")
            title(entry.get("title"))
            if not isinstance(entry.get("cards"), list):
                raise BookError("NFC associations could not be read.")
            if (type(entry.get("seconds")) not in (float, int)
                    or not math.isfinite(entry["seconds"]) or not 0 < entry["seconds"] <= MAX_SECONDS
                    or type(entry.get("bytes")) is not int or entry["bytes"] <= 0):
                raise BookError("The library could not be read.")
            for uid in entry["cards"]:
                if normalize_uid(uid) != uid or uid in cards:
                    raise BookError("NFC associations could not be read.")
                cards.add(uid)
        return data

    def public(self):
        data = self.load()
        self.root.mkdir(parents=True, exist_ok=True)
        disk = shutil.disk_usage(self.root)
        return {
            "books": [{"id": key, "title": entry["title"], "seconds": entry["seconds"],
                       "bytes": entry["bytes"], "paired": bool(entry["cards"])}
                      for key, entry in sorted(data["books"].items(), key=lambda item: item[1]["title"].casefold())],
            "free_bytes": disk.free, "total_bytes": disk.total,
            "max_upload_bytes": MAX_UPLOAD_BYTES,
        }

    def path_for(self, key):
        key = book_id(key)
        if key not in self.load()["books"]:
            raise BookError("Book not found.")
        path = self.root / f"{key}.wav"
        if not path.is_file() or path.is_symlink():
            raise BookError("The audio file for this book is unavailable.")
        return path

    def contains_card(self, uid):
        return self.for_card(uid) is not None

    def for_card(self, uid):
        uid = normalize_uid(uid)
        return next((key for key, value in self.load()["books"].items() if uid in value["cards"]), None)

    def change(self, key, action, value=None):
        key = book_id(key)
        with _locked_path(self.path):
            data = self.load()
            if key not in data["books"]:
                raise BookError("Book not found.")
            if action == "rename":
                data["books"][key]["title"] = title(value)
            elif action == "unpair":
                data["books"][key]["cards"] = []
            elif action == "delete":
                del data["books"][key]
            else:
                raise BookError("Unknown action.")
            _atomic_json(self.path, data)
            if action == "delete":
                (self.root / f"{key}.wav").unlink(missing_ok=True)

    def pair(self, key, uid, contacts):
        key, uid = book_id(key), normalize_uid(uid)
        # Same lock order as contact assignment: contacts, then library.
        with contacts._locked():
            if contacts.resolve_card(uid) is not None:
                raise BookError("This card belongs to a WhatsApp contact. Unpair it first.")
            with _locked_path(self.path):
                data = self.load()
                if key not in data["books"]:
                    raise BookError("Book not found.")
                for entry in data["books"].values():
                    if uid in entry["cards"]:
                        entry["cards"].remove(uid)
                data["books"][key]["cards"] = [uid]
                _atomic_json(self.path, data)

    def upload(self, source, length, filename, *, upload_id=None, run=subprocess.run):
        if upload_id is not None and not re.fullmatch(r"[0-9a-f]{32}", upload_id):
            raise BookError("Invalid upload identifier.")
        suffix = Path(filename).suffix.lower()
        if suffix not in FORMATS:
            raise BookError("Unsupported format: use MP3, WAV, OGG, M4A, FLAC or AAC.")
        if not 0 < length <= MAX_UPLOAD_BYTES:
            raise BookError("The file is empty or exceeds the 256 MB limit.")
        name = title(Path(filename.replace("\\", "/")).stem[:120])
        self.root.mkdir(parents=True, exist_ok=True)
        # Serialize large transfers, reserve room for decoding, and never expose a partial book.
        with _locked_path(self.root / "upload"):
            for stale in self.root.glob(".upload-*"):
                if stale.is_file():
                    stale.unlink()
            with _locked_path(self.path):
                known = self.load()["books"]
                # Persist the token with the book so a lost HTTP response is safe to retry.
                if upload_id is not None:
                    for key, entry in known.items():
                        if entry.get("upload_id") == upload_id:
                            if entry.get("source_name") != filename or entry.get("source_bytes") != length:
                                raise BookError("This upload identifier belongs to another file.")
                            self.path_for(key)
                            remaining = length
                            while remaining:
                                chunk = source.read(min(remaining, 1024 * 1024))
                                if not chunk:
                                    raise BookError("Upload interrupted. Please try again.")
                                remaining -= len(chunk)
                            return key
                # Recover interruption between media rename and catalogue commit (or deletion).
                for orphan in self.root.glob("*.wav"):
                    if re.fullmatch(r"[0-9a-f]{32}", orphan.stem) and orphan.stem not in known:
                        orphan.unlink()
            if shutil.disk_usage(self.root).free < length + MAX_WAV_BYTES + RESERVE_BYTES:
                raise BookError("Not enough space on the microSD to import this book.")
            upload_path = output_path = None
            try:
                with tempfile.NamedTemporaryFile(dir=self.root, prefix=".upload-", delete=False) as handle:
                    upload_path = Path(handle.name)
                    remaining = length
                    while remaining:
                        chunk = source.read(min(remaining, 1024 * 1024))
                        if not chunk:
                            raise BookError("Upload interrupted. Please try again.")
                        handle.write(chunk)
                        remaining -= len(chunk)
                    handle.flush()
                    os.fsync(handle.fileno())
                output_path = self.root / f".upload-{uuid.uuid4().hex}.wav"
                result = run([
                    "ffmpeg", "-nostdin", "-v", "error", "-xerror", "-y",
                    "-protocol_whitelist", "file,pipe", "-f", FORMATS[suffix], "-i", str(upload_path),
                    "-map", "0:a:0", "-vn", "-map_metadata", "-1", "-ac", "1", "-ar", "24000",
                    "-c:a", "pcm_s16le", "-t", str(MAX_SECONDS + 1), "-fs", str(MAX_WAV_BYTES),
                    "-f", "wav", str(output_path),
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600, check=False)
                if result.returncode:
                    raise BookError("The audio file is unreadable or unsupported.")
                with wave.open(str(output_path), "rb") as audio:
                    seconds = audio.getnframes() / audio.getframerate()
                if not 0 < seconds <= MAX_SECONDS:
                    raise BookError("The book must be no longer than one hour.")
                key = uuid.uuid4().hex
                with open(output_path, "rb") as handle:
                    os.fsync(handle.fileno())
                os.chmod(output_path, 0o600)
                with _locked_path(self.path):
                    data = self.load()
                    final = self.root / f"{key}.wav"
                    os.replace(output_path, final)
                    data["books"][key] = {"title": name, "cards": [], "seconds": seconds, "bytes": final.stat().st_size}
                    if upload_id is not None:
                        data["books"][key].update(upload_id=upload_id, source_name=filename, source_bytes=length)
                    try:
                        _atomic_json(self.path, data)
                    except Exception:
                        final.unlink(missing_ok=True)
                        raise
                return key
            except OSError as exc:
                if exc.errno == errno.ENOSPC:
                    raise BookError("The microSD is full. Free up space and try again.") from exc
                raise BookError("The book could not be saved to the microSD.") from exc
            except (subprocess.SubprocessError, wave.Error, EOFError) as exc:
                raise BookError("Import failed. Check the file and try again.") from exc
            finally:
                for path in (upload_path, output_path):
                    if path is not None:
                        path.unlink(missing_ok=True)


class BookRuntime:
    def __init__(self, path=BOOK_RUNTIME, *, clock=time.time):
        self.path, self.clock = Path(path), clock

    def _load(self):
        return _load_json(self.path, {})

    def reset_player(self):
        with _locked_path(self.path):
            data = self._load()
            data.pop("request", None)
            data.pop("player", None)
            data.pop("pairing_sound", None)
            _atomic_json(self.path, data)

    def begin_pair(self, key):
        with _locked_path(self.path):
            data = self._load()
            data["pairing"] = {"book": book_id(key), "expires": self.clock() + 120, "status": "waiting"}
            _atomic_json(self.path, data)

    def cancel_pair(self):
        with _locked_path(self.path):
            data = self._load()
            data.pop("pairing", None)
            _atomic_json(self.path, data)

    def scan(self, uid, library, contacts, *, new_presentation, contact_enrollment=False):
        with _locked_path(self.path):
            data = self._load()
            pairing = data.get("pairing", {})
            if new_presentation and pairing.get("status") == "waiting" and pairing.get("expires", 0) > self.clock():
                try:
                    if contact_enrollment:
                        raise BookError("Contact pairing is in progress. Finish it before pairing a book.")
                    library.pair(pairing["book"], uid, contacts)
                    pairing["status"] = "paired"
                    data["pairing_sound"] = self.clock()
                except BookError as exc:
                    pairing.update(status="error", error=str(exc))
                _atomic_json(self.path, data)
                return True
            key = library.for_card(uid)
            if key is None:
                return False
            if new_presentation:
                data["request"] = {"book": key, "created": self.clock()}
                _atomic_json(self.path, data)
            return True

    def take_pairing_sound(self):
        with _locked_path(self.path):
            data = self._load()
            created = data.pop("pairing_sound", None)
            if created is not None:
                _atomic_json(self.path, data)
                return 0 <= self.clock() - created < MAX_SECONDS + 120
        return False

    def take(self):
        with _locked_path(self.path):
            data = self._load()
            request = data.pop("request", None)
            if request is not None:
                _atomic_json(self.path, data)
                if 0 <= self.clock() - request.get("created", 0) < 10:
                    return book_id(request.get("book"))
        return None

    def player(self, key=None, *, paused=False, error=None):
        with _locked_path(self.path):
            data = self._load()
            data["player"] = {"book": key, "paused": paused, "error": error, "updated": self.clock()}
            _atomic_json(self.path, data)

    def public(self):
        data = self._load()
        pairing = data.get("pairing")
        if pairing and pairing.get("status") == "waiting" and pairing.get("expires", 0) <= self.clock():
            pairing = {**pairing, "status": "expired"}
        player = data.get("player", {})
        if not 0 <= self.clock() - player.get("updated", 0) < 5:
            player = {"error": player["error"]} if player.get("error") else {}
        return {"pairing": pairing, "player": player}


def card_is_book(contacts_path, uid):
    """Called under the contact lock to prevent ambiguous card assignments."""
    return BookLibrary(Path(contacts_path).parent.parent / "audio-books").contains_card(uid)
