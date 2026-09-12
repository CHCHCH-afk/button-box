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
service definitions. Record the source commit if known; otherwise record that
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

These are commands **on the Pi**, from the isolated checkout of the selected
commit, as the verified non-root sudo-capable account:

```sh
sudo messageboxctl stop
./scripts/setup.sh
```

Take/verify the consistent backup after stopping services and before running
setup; the two commands above do not create a backup. Alternatively use the
repository's `scripts/provision.sh` from a supported computer environment with
the verified SSH target; inspect its prerequisites first. Do not run POSIX shell
commands directly as PowerShell commands or assume local tools are on the Pi.

Setup installs to fixed paths; `git pull` alone does not update the application.
It leaves runtime services stopped. On an existing working installation, use
the **update** completion instructions and restore the prior service state.
For a box whose runtime was previously active:

```sh
sudo messageboxctl start
messageboxctl services
```

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
