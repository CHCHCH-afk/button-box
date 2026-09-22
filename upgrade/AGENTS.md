# Upgrade an existing box to this fork

This is an operator guide for a coding agent assisting a person with an
**already installed** box. Read the root `AGENTS.md` as well. The destination
repository is `https://github.com/CHCHCH-afk/button-box`; the upstream repository
is `https://github.com/button-box/button-box`.

The objective is a working upgrade with preserved data and a usable rollback,
not merely a successful Git checkout. Use the person's language for guidance;
the dashboard and repository documentation are in English.

## Names and connection: do not guess

- Upstream's public product name is **Button Box**. Installed packages, commands
  and service names use **messagebox**. Keep those exact identifiers.
- An SSH hostname is device configuration, not branding. Both `message-box-*`
  and `button-box-*` may exist. Never replace one prefix with the other or rename
  the Pi as part of an upgrade.
- Obtain the SSH account and a hostname/IP that the user already uses, or discover
  them from authorized local configuration. Do not assume `admin`, a particular
  box number, a private IP, or passwordless sudo. Do not scan unrelated networks.
- Verify host keys normally. A changed key needs investigation; do not disable
  host-key checking. Keep passwords and private keys in the local terminal or
  approved credential mechanism, never in chat or repository files.
- Reuse the verified target for every command. Mark whether each command runs
  **on the computer** or **on the Pi**. `wlan0` is a network interface, not a port;
  discover the configured dashboard port before constructing its URL.
- If the Pi is off or the user defers installation, finish the local preparation
  and report the remaining steps. Do not try to wake it or claim deployment.

## 1. Inspect before changing anything

Once connected, collect only the relevant facts, keeping private output local:

```sh
# On the Pi, through the verified SSH connection:
hostname
cat /proc/device-tree/model
cat /etc/os-release
uname -m
messageboxctl services
aplay -l
arecord -l
df -h / /var/lib/messagebox
```

Check `/opt/messagebox`, `/etc/messagebox/env`, the current source checkout and
service definitions. Read `/opt/messagebox/release.json` first, or the legacy `SOURCE_COMMIT` if no release record exists. Record the source commit if known; otherwise record that
it is unknown and preserve the installed files. A checkout's HEAD is not proof
that its files were installed. Inspect dirty Git state and preserve local
changes; never use `reset --hard` or overwrite a personal checkout.

Read only the necessary non-secret configuration fields. Do not print the whole
environment file, WhatsApp authentication store, contacts, raw NFC identifiers,
message filenames/IDs or recordings into shared logs or PRs.

Confirm the OS and board meet the selected commit's installer requirements.
Do not bypass installer checks on an unsupported board. If another layout or a
much older schema is installed, investigate the migration before running setup.

## 2. Select an exact source version

Use an isolated checkout of this fork. Choose and record an exact commit, and
inspect its changes relative to the installed version. Check `README.md`,
`docs/installation.md`, `docs/audio-books.md`, and `docs/audio-volume.md` if present.

**Do not assume an open PR is included in `main`.** Verify the selected tree
contains every requested feature. Upload retry/NFC confirmation and software
volume were developed in separate PRs. If features remain unmerged, prepare a
local integration branch and test it, and clearly identify that build to the
user. Do not merge public PRs or change the fork's default branch merely to
perform an installation.

Run `make check` on the exact tree to be installed in a suitable development
environment. The target Pi does not need the development toolchain. Check the
installer's explicit runtime/static allowlists when new files are involved.

## 3. Prepare backup and rollback

Explain the short interruption and intended build. An authorized upgrade
includes its ordinary read-only checks and preparation; do not repeatedly ask
for permission already given. If administrative authentication is required,
prepare the concrete command first and let the user authenticate locally.

Record which services are active/enabled. For a consistent backup, stop the
application writers before copying live application state. Verify sufficient
space for the backup, existing books, and the installation.

Prefer a verified private snapshot/image of the microSD when available. For a
file backup, preserve ownership, permissions and all installed components needed
to restore this device, including:

- `/opt/messagebox` and `/etc/messagebox`;
- `/var/lib/messagebox` in full: WhatsApp authentication, queue/outbox, contacts,
  NFC mappings, audio books and other persistent state;
- `/var/lib/messagebox-settings`, plus existing onboarding configuration/state
  under `/etc/messagebox-onboarding` and `/var/lib/messagebox-onboarding`;
- installed service units/drop-ins and any device-specific audio, network or
  boot configuration the selected installer may change.

Do not archive `/run` as durable state or restore an old playback request.
Backups contain credentials and family audio: keep them private and out of Git.
Check archive readability, file coverage and a restore destination before
proceeding. Record the backup location and exact rollback procedure locally.
Reverting Git alone does not revert `/opt`, installed units or migrated state.

## 4. Install the reviewed tree

For an existing installation, prefer the [manifest-bounded updater](../docs/bounded-updates.md).
It updates only the reviewed installed-file manifest, preserves private state,
records `/opt/messagebox/release.json`, and rolls back program files and service
state automatically on failure. It includes this fork's Audio Book modules and
software-volume configuration. Do not download upstream release packages in
place of this fork's exact merged source tree.

Generate `release-manifest.json` from that exact commit after `make check`.
Transfer the package, verify its checksum, and extract it into a new root-owned,
non-group-writable staging directory as described in the bounded-update guide.
Prepare the full private backup from section 3 as well; the bounded rollback
itself covers program files and boot selection, not private messages or books.
If stopping services to take the private backup, restore their recorded active
state before calling the updater so it can capture the correct restart set.

Check the Pi has the expected Python, ffmpeg/ffprobe, ALSA, GPIO and NFC runtime
dependencies. The updater does not install OS packages. Verify the existing
microphone and speaker names before proceeding: runtime detection preserves
configured `plughw:CARD=...,DEV=...` choices instead of switching to another
USB device. The new detector starts before previously active audio consumers.

On the Pi, replace RELEASE and BACKUP with concrete verified paths, then run:

```sh
sudo python3 /var/lib/button-box-update/RELEASE/scripts/install/bounded_update.py apply \
  --source-root /var/lib/button-box-update/RELEASE \
  --manifest /var/lib/button-box-update/RELEASE/release-manifest.json \
  --backup-dir /var/backups/button-box/BACKUP
messageboxctl services
```

For an older layout missing base dependencies, inspect `scripts/setup.sh` and
prepare a specific migration with backup first. Setup leaves services stopped;
restore only the previously active services afterward. Do not use setup merely
for a routine application update when the bounded updater is suitable.

Never reimage the card, reset Wi-Fi, initialize onboarding, relink WhatsApp,
reassign contacts/NFC cards or clear the library as part of a routine upgrade.
In particular, do not follow fresh-install `reset-wifi`/manufacturer handoff
instructions after updating an already configured box. Do not enable services
that were deliberately disabled without understanding the prior configuration.

If setup or startup fails, inspect a bounded, redacted error log and use the
prepared rollback when needed. Do not leave the user with an unexplained stopped
box. Report any unresolved dependency or hardware check honestly.

## 5. Validate actual behavior

Check the installed files match the selected build, the expected services are
active, the existing dashboard URL works, and the library/contacts/settings are
preserved. For software volume, start at a moderate setting (50% corresponds to
-20 dB in the documented configuration); do not substitute hardware PCM volume
for the application's `MessageBox` software control.

With the user's physical participation, validate a full WhatsApp message, a
book, volume changes during playback, mute/unmute, pause/resume, NFC pairing and
notification deferral. Receiving/sending acceptance messages needs an intended
recipient and user authorization; never send a test message autonomously.
After an agreed reboot, confirm saved volume, connectivity and library state.
Inspect USB disconnects if audio still cuts. A successful quiet test does not
prove the speaker, cable or power supply is healthy.

Finish with the installed commit, backup/rollback location, tests completed,
physical checks still pending and any unresolved issue. If installation was
deferred, state that clearly and provide the prepared next step instead of
claiming the box was upgraded.
