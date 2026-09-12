# Shared software volume

All application playback uses the `messagebox_volume` ALSA PCM: Audio Book,
WhatsApp playback and reviews, guided prompts, notifications, ringtone previews,
and NFC confirmations. `MSGBOX_SPK_DEV` continues to name the physical speaker;
`MSGBOX_SPEAKER_CARD` selects its ALSA control card. Capture is unchanged.

The dashboard volume slider saves when released and applies to audio already
playing. It saves only the volume; other unsaved form choices are preserved.
Saved settings are restored before the next playback after restart. An unavailable
speaker produces a warning on save, and playback never falls back to unattenuated
hardware when software-volume initialization fails.

The installed `/opt/messagebox/alsa.conf` includes the normal ALSA configuration
and adds a softvol stage with the `MessageBox` control. The scale is logarithmic:
0% is mute, 50% is -20 dB (10% signal amplitude), 60% is -16 dB (about 16%),
and 100% is the original signal level. No amplification is added. Start at 50%
on a speaker that disconnects during loud playback; test higher levels gradually.
Existing volume settings are preserved by the normal installer.

The first open after boot or USB reconnection creates the control using silence,
then applies the saved setting before any book, message or notification plays.
Changing the volume of active playback writes the control without reopening the
PCM. See the [ALSA soft-volume plugin documentation](https://www.alsa-project.org/alsa-doc/alsa-lib/pcm_plugins.html).

## Update and acceptance

Use the normal `scripts/setup.sh` update with services stopped. The setup and
provision allowlists include the new module and ALSA configuration. No settings
schema migration, library conversion or WhatsApp relink is required.

After updating, check a full book and WhatsApp message that previously failed.
During each, release the slider at 50%, then 0% (mute), then 60%, and confirm the
change without restarting playback. Test pause/resume, notifications, preview
and NFC confirmation. Reboot and confirm that the last saved volume returns.
Inspect kernel logs for USB disconnections. Attenuation avoiding a disconnect
does not establish whether its underlying cause is speaker electronics, cable,
power delivery or a driver; persistent failures still need hardware diagnosis.
