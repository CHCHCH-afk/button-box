"""Book playback in the button owner; pauses are intentionally memory-only."""

import fcntl
import os
import signal
import subprocess
import time
from contextlib import ExitStack

from messagebox.audio_books import BookError, BookLibrary, BookRuntime
from messagebox.runtime_paths import RUNTIME_DIR


def audio_lock(*, blocking=True):
    path = RUNTIME_DIR / "audio-book-playback.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+b")
    try:
        os.fchmod(handle.fileno(), 0o600)
        fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
    except Exception:
        handle.close()
        raise
    return handle


def stop(process):
    if process is not None and process.poll() is None:
        # A paused child must be resumed so SIGTERM can complete.
        try:
            process.send_signal(signal.SIGCONT)
            process.terminate()
        except ProcessLookupError:
            process.wait(timeout=2)
            return
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


def play_pending(button, led, speaker, *, library=None, runtime=None,
                 popen=subprocess.Popen, sleep=time.sleep, clock=time.monotonic):
    library, runtime = library or BookLibrary(), runtime or BookRuntime()
    if runtime.take_pairing_sound():
        # Reuse the original pairing chime in the audio owner, after any current audio.
        from messagebox.onboarding.nfc import TonePlayer

        try:
            with audio_lock():
                TonePlayer(directory=RUNTIME_DIR / "audio-book-tones")("success")
        except (OSError, subprocess.SubprocessError):
            runtime.player(error="Card paired, but the confirmation sound could not be played.")
    key = runtime.take()
    if key is None:
        return False
    process = None
    error = None
    try:
        with audio_lock(), ExitStack() as cleanup:
            # Stop the child before another process can acquire the speaker lease.
            cleanup.callback(lambda: stop(process))
            paused = False
            # Debounce both edges; holding a button toggles only once.
            stable = raw = bool(button.is_pressed)
            changed = clock()
            heartbeat = 0.0
            while True:
                replacement = runtime.take()
                if replacement is not None:
                    key = replacement
                    stop(process)
                    process = None
                    paused = False
                if process is None:
                    path = library.path_for(key)
                    process = popen(["aplay", "-q", "-D", speaker, str(path)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    runtime.player(key)
                led.off()
                if process.poll() is not None:
                    if process.returncode:
                        raise BookError("Playback failed. Check the speaker and try again.")
                    break
                now = clock()
                pressed = bool(button.is_pressed)
                if pressed != raw:
                    raw, changed = pressed, now
                if raw != stable and now - changed >= (0.08 if raw else 0.2):
                    stable = raw
                    if stable:
                        paused = not paused
                        process.send_signal(signal.SIGSTOP if paused else signal.SIGCONT)
                        runtime.player(key, paused=paused)
                if now - heartbeat >= 1:
                    runtime.player(key, paused=paused)
                    heartbeat = now
                sleep(0.01)
    except (BookError, OSError, subprocess.SubprocessError):
        error = "Playback failed. Check the book and speaker, then scan the card again."
    finally:
        stop(process)
        runtime.player(error=error)
    # Absorb the last pause/resume press so it cannot become a recording.
    released_at = None
    while released_at is None or clock() - released_at < 0.2:
        if button.is_pressed:
            released_at = None
        elif released_at is None:
            released_at = clock()
        sleep(0.01)
    return True
