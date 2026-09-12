import io
import json
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from messagebox.audio_books import BookError, BookLibrary, BookRuntime, MAX_UPLOAD_BYTES
from messagebox.contacts import ContactError, ContactStore
from messagebox.nfc import NfcRuntime
from messagebox.nfc_state import AnnouncementStore, EnrollmentStore, NfcRouter, SelectionStore

CARD = "04:A1:00:FF"
OTHER_CARD = "04:A1:00:EE"
CONTACT = "15551234567@s.whatsapp.net"


def wav_bytes():
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"\0\0" * 2400)
    return output.getvalue()


def convert(command, **kwargs):
    Path(command[-1]).write_bytes(wav_bytes())
    return SimpleNamespace(returncode=0)


class AudioBooksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.library = BookLibrary(root / "audio-books")
        self.contacts = ContactStore(root / "state" / "contacts.json")
        self.now = 1000
        self.runtime = BookRuntime(root / "run" / "books.json", clock=lambda: self.now)

    def add_book(self, name="Story.wav"):
        raw = wav_bytes()
        return self.library.upload(io.BytesIO(raw), len(raw), name, run=convert)

    def test_upload_pair_rename_restart_unpair_delete(self):
        key = self.add_book()
        self.runtime.begin_pair(key)
        self.assertTrue(self.runtime.scan(CARD, self.library, self.contacts, new_presentation=True))
        self.assertEqual(self.runtime.public()["pairing"]["status"], "paired")
        self.assertIsNone(self.runtime.take(), "pairing must not start playback")
        self.library.change(key, "rename", "My short book")
        restored = BookLibrary(self.library.root)
        self.assertEqual(restored.for_card(CARD), key)
        public = restored.public()
        self.assertNotIn(CARD, json.dumps(public))
        self.assertEqual(public["books"][0]["title"], "My short book")
        restored.change(key, "unpair")
        self.assertIsNone(restored.for_card(CARD))
        restored.change(key, "delete")
        self.assertFalse((restored.root / f"{key}.wav").exists())
        self.assertEqual(restored.public()["books"], [])

    def test_contact_and_book_card_assignments_cannot_overlap_either_direction(self):
        key = self.add_book()
        self.contacts.add_contact(CONTACT, "Family", receive_after=0)
        self.contacts.assign_card(CONTACT, CARD)
        with self.assertRaises(BookError):
            self.library.pair(key, CARD, self.contacts)
        self.contacts.remove_card(CARD)
        self.library.pair(key, CARD, self.contacts)
        with self.assertRaises(ContactError):
            self.contacts.assign_card(CONTACT, CARD)
        with self.assertRaises(ContactError):
            self.contacts.enroll_card(CONTACT, CARD, label="Family")
        self.assertIsNone(self.contacts.resolve_card(CARD))
        self.assertEqual(self.library.for_card(CARD), key)

    def test_retry_after_lost_response_survives_restart_without_duplicate(self):
        raw = wav_bytes()
        token = "b" * 32
        key = self.library.upload(io.BytesIO(raw), len(raw), "Story.wav", upload_id=token, run=convert)
        self.library.change(key, "rename", "Renamed")
        restored = BookLibrary(self.library.root)
        decoder = mock.Mock(side_effect=AssertionError("must not decode twice"))
        self.assertEqual(restored.upload(io.BytesIO(raw), len(raw), "Story.wav", upload_id=token, run=decoder), key)
        self.assertEqual(len(restored.public()["books"]), 1)
        self.assertEqual(restored.public()["books"][0]["title"], "Renamed")
        with self.assertRaises(BookError):
            restored.upload(io.BytesIO(raw), len(raw), "Other.wav", upload_id=token, run=decoder)
        self.assertNotIn("upload_id", json.dumps(restored.public()))

    def test_retry_after_partial_upload_can_complete(self):
        raw, token = wav_bytes(), "c" * 32
        with self.assertRaises(BookError):
            self.library.upload(io.BytesIO(raw[:10]), len(raw), "Story.wav", upload_id=token, run=convert)
        key = self.library.upload(io.BytesIO(raw), len(raw), "Story.wav", upload_id=token, run=convert)
        self.assertTrue(self.library.path_for(key).exists())
        self.assertEqual(len(self.library.public()["books"]), 1)

    def test_pairing_confirmation_is_once_only_and_only_after_success(self):
        key = self.add_book()
        self.runtime.begin_pair(key)
        self.runtime.scan(CARD, self.library, self.contacts, new_presentation=True, contact_enrollment=True)
        self.assertFalse(self.runtime.take_pairing_sound())
        self.runtime.begin_pair(key)
        self.runtime.scan(CARD, self.library, self.contacts, new_presentation=True)
        self.assertTrue(self.runtime.take_pairing_sound())
        self.runtime.scan(CARD, self.library, self.contacts, new_presentation=False)
        self.assertFalse(self.runtime.take_pairing_sound())

    def test_card_reassignment_is_single_and_replaces_previous_card(self):
        one, two = self.add_book(), self.add_book("Two.mp3")
        self.library.pair(one, CARD, self.contacts)
        self.library.pair(two, CARD, self.contacts)
        self.library.pair(two, OTHER_CARD, self.contacts)
        self.assertIsNone(self.library.for_card(CARD))
        self.assertEqual(self.library.for_card(OTHER_CARD), two)
        self.assertFalse(self.library.load()["books"][one]["cards"])

    def test_interrupted_invalid_and_failed_conversion_never_expose_partial_books(self):
        for source, length, name, run in (
            (b"partial", 100, "Story.wav", convert),
            (b"x", 1, "Story.html", convert),
            (b"x", MAX_UPLOAD_BYTES + 1, "Story.wav", convert),
            (b"x", 1, "Story.wav", lambda *a, **k: SimpleNamespace(returncode=1)),
        ):
            with self.subTest(name=name, length=length), self.assertRaises(BookError):
                self.library.upload(io.BytesIO(source), length, name, run=run)
            self.assertEqual(self.library.public()["books"], [])
            self.assertEqual(list(self.library.root.glob(".upload-*")), [])

    def test_full_card_and_conversion_timeout_have_safe_errors(self):
        with mock.patch("messagebox.audio_books.shutil.disk_usage", return_value=SimpleNamespace(free=0)):
            with self.assertRaisesRegex(BookError, "microSD"):
                self.add_book()
        with self.assertRaises(BookError):
            self.library.upload(io.BytesIO(b"x"), 1, "Book.mp3",
                                run=mock.Mock(side_effect=subprocess.TimeoutExpired("ffmpeg", 600)))
        self.assertEqual(list(self.library.root.glob(".upload-*")), [])

    def test_expired_cancelled_and_conflicting_pairing(self):
        key = self.add_book()
        self.runtime.begin_pair(key)
        self.now += 121
        self.assertEqual(self.runtime.public()["pairing"]["status"], "expired")
        self.assertFalse(self.runtime.scan(CARD, self.library, self.contacts, new_presentation=True))
        self.runtime.begin_pair(key)
        self.runtime.scan(CARD, self.library, self.contacts, new_presentation=True, contact_enrollment=True)
        self.assertEqual(self.runtime.public()["pairing"]["status"], "error")
        self.assertIsNone(self.library.for_card(CARD))
        self.runtime.cancel_pair()
        self.assertIsNone(self.runtime.public()["pairing"])

    def test_runtime_debounces_scan_and_restarts_only_after_removal(self):
        key = self.add_book()
        self.library.pair(key, CARD, self.contacts)
        root = self.runtime.path.parent
        router = NfcRouter(self.contacts, SelectionStore(root / "selection"), EnrollmentStore(root / "enrollment"))
        announcer = mock.Mock()
        runtime = NfcRuntime(router, announcer, books=self.library, book_runtime=self.runtime)
        self.assertEqual(runtime.observe(CARD, 1).action, "audio_book")
        self.assertEqual(self.runtime.take(), key)
        runtime.observe(CARD, 2)
        self.assertIsNone(self.runtime.take())
        runtime.observe(None, 3)
        runtime.observe(CARD, 4)
        self.assertEqual(self.runtime.take(), key)
        self.assertIsNone(router.selection.load())
        self.assertIsNone(AnnouncementStore(root / "nfc-announcement.json").take())

    def test_restart_discards_request_and_pause_but_preserves_pairings(self):
        key = self.add_book()
        self.library.pair(key, CARD, self.contacts)
        self.runtime.scan(CARD, self.library, self.contacts, new_presentation=True)
        self.runtime.player(key, paused=True)
        self.runtime.reset_player()
        self.assertIsNone(self.runtime.take())
        self.assertEqual(self.runtime.public()["player"], {})
        self.assertEqual(self.library.for_card(CARD), key)

    def test_path_traversal_is_rejected(self):
        for key in ("../library.json", "/etc/passwd", "x", None):
            with self.subTest(key=key), self.assertRaises(BookError):
                self.library.change(key, "delete")

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg integration requires installed decoder")
    def test_real_decoder_accepts_wav_and_rejects_disguised_text(self):
        raw = wav_bytes()
        key = self.library.upload(io.BytesIO(raw), len(raw), "A real story.wav")
        with wave.open(str(self.library.path_for(key)), "rb") as handle:
            self.assertEqual(handle.getnchannels(), 1)
            self.assertEqual(handle.getframerate(), 24000)
        with self.assertRaises(BookError):
            self.library.upload(io.BytesIO(b"not audio"), 9, "Fake.mp3")
