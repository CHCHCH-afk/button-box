"""Shared ALSA software volume for every Message Box playback path."""

import os
import subprocess
import threading

from messagebox.runtime_paths import APP_DIR
from messagebox.settings import SettingsError, SettingsStore

SOFTWARE_DEVICE = "messagebox_volume"
VOLUME_WARNING = "Settings saved, but the speaker volume could not be applied. Check the speaker connection."
_lock = threading.Lock()


def apply_volume(settings=None, *, run=None):
    """Apply saved volume, recreating the soft control after boot or USB reconnect."""
    run = run or subprocess.run
    with _lock:
        try:
            if settings is None:
                settings, _ = SettingsStore().load()
            percent = settings["master_volume_percent"]
            if type(percent) is not int or not 0 <= percent <= 100:
                return False
            os.environ["ALSA_CONFIG_PATH"] = str(APP_DIR / "alsa.conf")
            command = ["amixer", "-q", "-c", os.environ.get("MSGBOX_SPEAKER_CARD", "Device"),
                       "sset", "MessageBox", f"{percent}%"]
            options = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, check=False)
            if run(command, **options).returncode == 0:
                return True
            # ALSA creates the user volume control on the first PCM open. Only
            # silence is played until the requested attenuation has been applied.
            initialized = run(["aplay", "-q", "-D", SOFTWARE_DEVICE, "-t", "raw",
                               "-f", "S16_LE", "-c", "2", "-r", "48000"],
                              input=b"\0" * 9600, **options)
            return initialized.returncode == 0 and run(command, **options).returncode == 0
        except (OSError, subprocess.SubprocessError, SettingsError):
            return False


def playback_device(*, run=None):
    if not apply_volume(run=run):
        # Never bypass failed volume setup by playing straight to the hardware.
        raise OSError("Speaker volume unavailable")
    return SOFTWARE_DEVICE
