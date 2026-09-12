import os
import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

from messagebox import audio_volume as audio


class AudioVolumeTests(unittest.TestCase):
    def setUp(self):
        environment = mock.patch.dict(os.environ, {"MSGBOX_SPEAKER_CARD": "speaker"})
        environment.start()
        self.addCleanup(environment.stop)

    def test_first_open_is_silent_and_volume_is_applied_before_playback(self):
        run = mock.Mock(side_effect=[SimpleNamespace(returncode=n) for n in [1, 0, 0]])
        self.assertTrue(audio.apply_volume({"master_volume_percent": 50}, run=run))
        first, silence, last = run.call_args_list
        self.assertEqual(first.args[0], ["amixer", "-q", "-c", "speaker", "sset", "MessageBox", "50%"])
        self.assertEqual(first.args, last.args)
        self.assertEqual(silence.args[0][3], audio.SOFTWARE_DEVICE)
        self.assertEqual(set(silence.kwargs["input"]), {0})
        self.assertTrue(os.environ["ALSA_CONFIG_PATH"].endswith("/alsa.conf"))

    def test_live_volume_does_not_reopen_active_pcm(self):
        run = mock.Mock(return_value=SimpleNamespace(returncode=0))
        for percent in [15, 0, 60]:
            self.assertTrue(audio.apply_volume({"master_volume_percent": percent}, run=run))
        self.assertTrue(all(call.args[0][0] == "amixer" for call in run.call_args_list))
        self.assertEqual(run.call_args_list[1].args[0][-1], "0%")

    def test_missing_speaker_cannot_fall_back_to_unattenuated_audio(self):
        with mock.patch.object(audio, "apply_volume", return_value=False):
            with self.assertRaises(OSError):
                audio.playback_device()
        for failure in [OSError(), subprocess.TimeoutExpired("amixer", 3)]:
            self.assertFalse(audio.apply_volume({"master_volume_percent": 50}, run=mock.Mock(side_effect=failure)))

    def test_restart_uses_persisted_setting_and_bounds_are_checked(self):
        run = mock.Mock(return_value=SimpleNamespace(returncode=0))
        with mock.patch.object(audio, "SettingsStore") as store:
            store.return_value.load.return_value = ({"master_volume_percent": 35}, False)
            self.assertTrue(audio.apply_volume(run=run))
        self.assertEqual(run.call_args.args[0][-1], "35%")
        for invalid in [-1, 101, True, "50"]:
            run.reset_mock()
            self.assertFalse(audio.apply_volume({"master_volume_percent": invalid}, run=run))
            run.assert_not_called()
