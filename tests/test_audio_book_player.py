import signal
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

from messagebox import audio_book_player as player
from messagebox.audio_books import BookRuntime


class Clock:
    now = 0.0

    def sleep(self, delay):
        self.now += delay
        if self.now > 8:
            raise AssertionError("playback did not finish")


class Process:
    def __init__(self, clock, ends=2):
        self.clock, self.ends = clock, ends
        self.returncode = None
        self.signals = []
        self.paused = False

    def poll(self):
        if self.clock.now >= self.ends and not self.paused:
            self.returncode = 0
        return self.returncode

    def send_signal(self, sig):
        self.signals.append(sig)
        self.paused = sig == signal.SIGSTOP

    def terminate(self):
        self.returncode = -15

    def wait(self, timeout):
        return self.returncode


class PlayerTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.led = mock.Mock()
        self.library = mock.Mock()
        self.library.path_for.return_value = Path("/library/story.wav")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = BookRuntime(Path(self.temp.name) / "runtime", clock=lambda: self.clock.now)
        self.lock = mock.patch.object(player, "audio_lock", return_value=nullcontext())
        self.lock.start()
        self.addCleanup(self.lock.stop)

    def play(self, pressed, take, popen):
        clock = self.clock

        class Button:
            @property
            def is_pressed(self):
                return pressed(clock.now)

        with mock.patch.object(self.runtime, "take", side_effect=take):
            return player.play_pending(Button(), self.led, "default", library=self.library,
                                       runtime=self.runtime, popen=popen, clock=lambda: clock.now, sleep=clock.sleep)

    def test_pause_resume_debounces_and_never_saves_position(self):
        process = Process(self.clock, ends=2)
        requests = iter(["a" * 32])
        result = self.play(lambda t: 0.1 < t < 0.4 or 0.9 < t < 1.3,
                           lambda: next(requests, None), mock.Mock(return_value=process))
        self.assertTrue(result)
        self.assertEqual(process.signals, [signal.SIGSTOP, signal.SIGCONT])
        self.assertIsNone(self.runtime.public()["player"]["book"])
        self.assertNotIn("position", self.runtime.path.read_text())
        self.led.on.assert_not_called()

    def test_rescan_replaces_even_paused_playback_from_beginning(self):
        sent = set()
        processes = []

        def take():
            slot = 1 if self.clock.now >= 0.8 else 0
            if slot not in sent:
                sent.add(slot)
                return "a" * 32
            return None

        def popen(command, **kwargs):
            self.assertEqual(command, ["aplay", "-q", "-D", "default", "/library/story.wav"])
            process = Process(self.clock, ends=2)
            processes.append(process)
            return process

        self.play(lambda t: 0.1 < t < 0.4, take, popen)
        self.assertEqual(len(processes), 2)
        self.assertEqual(processes[0].returncode, -15)
        self.assertEqual(processes[0].signals, [signal.SIGSTOP, signal.SIGCONT])

    def test_playback_failure_clears_busy_status(self):
        requests = iter(["a" * 32])
        self.play(lambda t: False, lambda: next(requests, None), mock.Mock(side_effect=OSError()))
        state = self.runtime.public()["player"]
        self.assertIsNone(state["book"])
        self.assertTrue(state["error"])

    def test_end_press_is_absorbed_until_release(self):
        requests = iter(["a" * 32])
        process = Process(self.clock, ends=0.1)
        self.play(lambda t: t < 0.6, lambda: next(requests, None), mock.Mock(return_value=process))
        self.assertGreaterEqual(self.clock.now, 0.8)

    def test_pairing_uses_original_success_chime_and_does_not_start_book(self):
        with mock.patch.object(self.runtime, "take_pairing_sound", return_value=True), \
                mock.patch("messagebox.onboarding.nfc.TonePlayer") as tone, \
                mock.patch.object(player, "audio_lock", return_value=nullcontext()) as lock:
            popen = mock.Mock()
            self.assertFalse(player.play_pending(mock.Mock(), self.led, "default",
                                                runtime=self.runtime, popen=popen))
            tone.return_value.assert_called_once_with("success")
            lock.assert_called_once()
            popen.assert_not_called()
