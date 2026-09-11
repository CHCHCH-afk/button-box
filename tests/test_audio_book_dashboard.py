import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from messagebox import audio_book_dashboard as api
from messagebox.audio_books import BookError, BookLibrary, BookRuntime
from messagebox.dashboard import app as dashboard


class DashboardBookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.library = BookLibrary(root / "audio-books")
        self.runtime = BookRuntime(root / "runtime")
        for name, value in (("BookLibrary", self.library), ("BookRuntime", self.runtime)):
            patcher = mock.patch.object(api, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def post(self, path, data=b"{}", **headers):
        handler = dashboard.Handler.__new__(dashboard.Handler)
        handler.path = path
        handler.headers = {"Host": "button-box.local", "Content-Type": "application/json",
                           "Content-Length": str(len(data)), **headers}
        handler.local_host = "button-box.local"
        handler.client_address = ("192.168.1.20", 12345)
        handler.rfile = io.BytesIO(data)
        responses = []
        handler._send = lambda code, body, *args: responses.append((code, json.loads(body)))
        handler.do_POST()
        return responses[0]

    def test_upload_streams_through_dashboard_and_returns_created_id(self):
        with mock.patch.object(self.library, "upload", return_value="a" * 32) as upload:
            code, data = self.post("/api/audio-books/upload", b"wave", **{
                "Content-Type": "application/octet-stream", "X-Audio-Filename": "Livre%20court.wav",
            })
        self.assertEqual(code, 201)
        self.assertTrue(data["ok"])
        self.assertEqual(upload.call_args.args[1:], (4, "Livre court.wav"))

    def test_cross_origin_upload_and_mutation_rejected_before_storage(self):
        for path in ("/api/audio-books", "/api/audio-books/upload"):
            with self.subTest(path=path), mock.patch.object(self.library, "upload") as upload:
                code, _ = self.post(path, Origin="https://untrusted.example")
                self.assertEqual(code, 403)
                upload.assert_not_called()

    def test_error_response_does_not_expose_paths(self):
        with mock.patch.object(self.library, "upload", side_effect=OSError("private/path")):
            code, data = self.post("/api/audio-books/upload", b"x", **{"Content-Type": "application/octet-stream"})
        self.assertEqual(code, 503)
        self.assertNotIn("private", json.dumps(data))
        with mock.patch.object(self.library, "upload", side_effect=BookError("The microSD is full.")):
            code, data = self.post("/api/audio-books/upload", b"x", **{"Content-Type": "application/octet-stream"})
        self.assertEqual(code, 400)
        self.assertIn("microSD", data["error"])

    def test_delete_is_blocked_during_paused_book(self):
        key = "a" * 32
        self.runtime.player(key, paused=True)
        with mock.patch.object(self.library, "change") as change:
            code, _ = self.post("/api/audio-books", json.dumps({"action": "delete", "id": key}).encode())
        self.assertEqual(code, 400)
        change.assert_not_called()

    def test_pair_requires_a_healthy_reader(self):
        with mock.patch.object(self.library, "path_for"), mock.patch.object(api, "NFC_HEALTH_FILE", Path(self.temp.name) / "missing"):
            code, data = self.post("/api/audio-books", json.dumps({"action": "pair", "id": "a" * 32}).encode())
        self.assertEqual(code, 400)
        self.assertIn("NFC", data["error"])
        self.assertIsNone(self.runtime.public()["pairing"])

    def test_installers_include_personal_modules_and_preserve_data(self):
        root = Path(__file__).resolve().parents[1]
        setup = (root / "scripts/setup.sh").read_text()
        provision = (root / "scripts/provision.sh").read_text()
        for name in ("audio_books.py", "audio_book_player.py", "audio_book_dashboard.py", "audio-books.js"):
            self.assertIn(name, setup)
            self.assertIn(name, provision)
        self.assertIn('"$DATA_DIR/audio-books"', setup)
        self.assertNotIn('rm -rf "$DATA_DIR', setup)
