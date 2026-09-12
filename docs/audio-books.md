# Audio Book — personal fork

This fork adds short, local audio books to Button Box. The household dashboard
has an **Audio Book** section. The existing WhatsApp setup is still required.

## Using the library

1. Open the normal household dashboard and select **Audio Book**.
2. Drop one or several audio files in the upload area, or choose files with the
   file picker. Each file becomes one book. MP3, WAV, OGG, M4A, FLAC and AAC are
   supported, up to 256 MiB per source file and one hour per book.
3. Wait for transfer and audio validation to finish. Only a successful import
   appears in the library. Files are converted to mono 24 kHz PCM WAV for the
   existing ALSA player; this uses about 2.9 MB per minute on the microSD.
4. Select **Pair NFC card**, remove any card already on the reader, then
   present the intended card within two minutes. Pairing does not play the book.
5. Remove and present the card again to play from the beginning. A brief button
   press pauses; the next press resumes. A held press toggles only once. No
   microphone recording starts during a book.

Removing a card does not stop playback. Every new presentation starts the
associated book from the beginning, including when the previous playback was
paused. Presenting another book card replaces the current book. Position is
never saved, and a reboot does not resume playback.

WhatsApp reception continues while a book plays or is paused. New-message
ringing and the button's arrival lamp wait until the book ends. Existing
arrival-signal and quiet-hours settings still apply when the book ends.
Manual ring requests and played-receipt announcements also wait. Messages are
not automatically played at the end: press the button to use the normal
WhatsApp flow. The caregiver's Activity page can still inspect the queue.

Rename books, change/remove their NFC association, or delete their files from
the library. A card has one purpose: a book or a WhatsApp contact. Unpair it
from its current purpose first when changing between these two uses. Pairing
an existing book card to another book moves the association. Pairing a new
card to a book replaces that book's old card.

## Storage, errors and recovery

- Media and the private catalogue are in `/var/lib/messagebox/audio-books/`,
  on the microSD in the normal Raspberry Pi OS installation. A system configured
  to boot/store `/var/lib` on another disk uses that disk instead.
- `library.json` contains titles and private NFC mappings. Neither it nor the
  audio files belongs in Git. Back up this directory privately before updates.
- `/run/messagebox/audio-books.json` contains short-lived pairing requests,
  pending scans and player status. It contains no bookmark. Old scan requests
  expire after ten seconds; scans made during a long WhatsApp interaction may
  need to be repeated afterward.
- Temporary imports are hidden. Failed/interrupted imports are removed, and
  leftovers after power loss are cleaned at the next import. The installer
  creates the library directory but does not replace its contents.
- Import reserves 64 MiB for the rest of the box plus enough space for a full
  decoded book, so it can reject an import before the microSD is completely full.
- The UI reports unsupported/corrupt files, full storage, interrupted transfers,
  reader unavailability and pairing expiry. After a lost upload response, check
  the library before retrying to avoid importing the same book twice.
- Pairing requires the normal NFC service to be running. During initial setup,
  the Audio Book page explains that imports become available after setup.
- If playback fails, an error appears in Audio Book. Check the speaker and
  present the card again. Restarting the button service clears a paused session.

## Install or update this fork

The source is `https://github.com/CHCHCH-afk/button-box`. Use this fork rather
than installing the upstream repository directly, which does not contain the
personal module.

```sh
git clone https://github.com/CHCHCH-afk/button-box.git
cd button-box
git remote add upstream https://github.com/button-box/button-box.git
make check
```

Follow [installation.md](installation.md) and the existing README for your
verified Pi model and SSH destination. Provisioning includes the personal
Python modules and the Audio Book browser script. `ffmpeg` and `aplay` are
already installed by the standard setup. No additional service, account,
environment variable, or public network listener is added. Installation ends
with services stopped; follow the existing activation procedure afterward.

To incorporate future upstream changes into a clean local checkout of your
personal `main` branch:

```sh
git switch main
git pull --ff-only origin main
git fetch upstream
git merge upstream/main
make check
git push origin main
```

Resolve any merge conflict before deploying. Do not reset your personal branch
to upstream or discard your commits when synchronizing the fork. Keep a private
backup and record the previously installed commit before provisioning a working
box. Updating source code does not erase the library; reimaging the microSD does.

## Your customizable files

Books and all other application sounds share the dashboard's
[software volume control](audio-volume.md), which also applies during playback.

| File | Purpose |
| --- | --- |
| `messagebox/audio_books.py` | Library, formats/size limits, NFC mapping and transient requests |
| `messagebox/audio_book_player.py` | Button pause/resume and restart-from-beginning behavior |
| `messagebox/audio_book_dashboard.py` | Upload and library API |
| `messagebox/onboarding/static/audio-books.js` | Personal dashboard interactions |

Small hooks remain in the NFC reader, contact assignment, button loop, dashboard,
shared HTML/navigation/styles, and installation allowlists. This separation
reduces merge conflicts but cannot guarantee compatibility with every future
upstream change. The button service owns book playback; ringtone previews use
the same audio lock. NFC identifiers are never returned by the library API.

## Validation before use on a physical box

Automated tests cover real WAV decoding (when ffmpeg is installed), corrupt and
interrupted uploads, storage exhaustion, private mappings, conflict prevention,
card debounce, restart/reset, paused playback replacement, button debounce,
deferred arrivals and dashboard origin checks. Run `make check`.

Physical Raspberry Pi acceptance is still required:

1. Upload a short known audio file and pair an unused NFC card.
2. Scan once; leave the card present and verify there is no restart loop.
3. Pause and resume using short and held button presses; confirm no recording.
4. Remove/rescan the same card, then a second book card; verify restart at zero.
5. Receive a WhatsApp message during playback and during a pause; verify no
   sound/lamp interruption, then the configured arrival signal at the end.
6. Reboot during a paused book; verify no automatic resume and preserved library.
7. Update from this fork and verify the library, associations and WhatsApp flow.
