# Lenovo LOQ 15IRX10 / 83JE: device audit

Status: **physical validation: audio processing operational and subjectively significant improvement**.

On 2026-09-28 the owner confirmed that the experimental package processes the
LOQ's built-in speakers and substantially improves perceived sound compared
with Linux audio without Nahimic. Windows OEM parity has not been evaluated:
no reference installation is available.
Stability and device-transition validation continues below.

Keep the DS575151 device settings and profiles unchanged. Changes to OEM DSP
parameters require a demonstrated reason; stability tests must preserve both
the downloaded OEM data and the user's saved parameters.

## Existing architecture and minimal extension

Before this change, MECHREVO Wujie 14X Pro was represented by the literal
`HDA:14f11f87,1d05e022,` plus `[Out] Speaker` in `host/desktop_audio.py`.
`host/entry.py` selected one matching sink and retained its node name in
`installation.json`; the service waited for that same speaker port to return.

`packaging/extract_runtime.py` extracted the runtime from the pinned Microsoft
Update `nahimic-apo4-4.14.cab` and the AIstone APO4
`NH3CNXTProductSettings.cab` from Nahimic's
restore tool. `runtime-sha256.json` selected and verified the DLLs, Global,
Metadata, `1D05E022_Speakers.nsx`, and the four audio profiles.

`host/run_local.py` copied the factory settings through `prepare_settings.py`.
The latter translates Metadata's default profile field into Global's Data
section without changing DSP values. The launcher read the device GUID from
the hardcoded MECHREVO filename and passed it as `--device-id` to the Wine host.
`apo_probe.cpp` also hardcoded that filename in its import list. It imports the
device, four profiles and Global through Nahimic's Expert API, binds the device
GUID, then runs the original SFX/MFX/EFX chain. Real endpoint volume comes from
`pulse_state`; PipeWire/WirePlumber route the speaker filter. The UI controls
Nahimic through `apo_control.exe`.

The initial extension used two entries in a small table in `desktop_audio.py`, using
the exact codec and subsystem pair plus a speaker port. Both the UCM
`[Out] Speaker` and ACP `analog-output-speaker` names are accepted. Headphones,
HDMI, USB and unknown codec/subsystem pairs do not select an OEM configuration.
The existing MECHREVO factory layout stays in place; Lenovo has its own
`factory/17AA3DCB/` set, including all four profiles, Global and Metadata.
The launcher selects the set and passes `--device-file` to the existing host.
Saved sessions must match the original endpoint, codec/subsystem and DLL hash;
the previous MECHREVO session format remains accepted.

No new DSP implementation, kernel/ALSA change, alternate host, or routing
architecture is introduced. Profile GUIDs in `app/backend.py` match both OEM
sets, so the UI control interface needs no change. The shared runtime remains
the pinned `nahimic-apo4-4.14.cab` binaries; DS575151 itself bundles APO 4.15.3.0.
Importing these settings into the existing runtime does not claim reproduction
of the entire Windows OEM audio stack.

## Exact OEM source

- Official document: [Lenovo DS575151](https://support.lenovo.com/np/en/downloads/ds575151-realtek-audio-driver-for-windows-11-64-bit-loq-15irx10).
- Version: `Realtek_6.0.9879.1_SST12181`, published 2025-12-08.
- Installer: [x7lo037f7bzmrbh0.exe](https://download.lenovo.com/consumer/mobiles/x7lo037f7bzmrbh0.exe).
- Installer SHA-256: `495e008eb0d1c22a7c4bec6de74bff920759eecaffaaa384ec7c35157f8f0557`.
- Extracted CAB: `code$GetExtractPath$/Audio9879/Driver/Nahimic/ExtINF_Path/NH3ProductSettings0.cab`.
- Device: `Devices/17AA3DCB_InternalSpeakers.nsx`, SHA-256
  `eaf4dde77db67c50fdbba7711f60529f9370fdb64e5b7997be1e2200a97bb143`.
- Device GUID: `{58b83e1f-e815-43e2-88b3-df21571f5e65}`; HWID
  `SUBSYS_17AA3DCB`; form factor `InternalSpeakers`.

`AVoluteNH3Ext.inf` matches `DEV_0257&SUBSYS_17AA3DCB` to
`RtkHDARender2_Install`, which selects CAB 0 and `VEN_AVOL&AID_0802`.
`A-VoluteNhApo4Swc.inf` maps that component to Nahimic APO 4.
The device XML comment names L390-15IRX9, but its exact hardware ID and Lenovo's
INF selection identify the file used here; no other laptop's tuning is substituted.

All seven Lenovo NSX files are extracted from this CAB and checked against
`packaging/runtime-sha256.json`. Even files whose hashes happen to match the
MECHREVO set retain their Lenovo provenance. Music differs: Lenovo sets
`kSet_VoiceBoostState=0`; the existing MECHREVO file sets it to 1.
The installer is extracted statically with innoextract, without running it.
Only selected runtime files enter the built package. OEM archives and working
material stay outside the source repository; extraction writes under the build
output directory and packaging performs no service activation.

## Validation

Read-only checks on the target machine identified:

| Item | Observed value |
| --- | --- |
| DMI | `83JE`, `LOQ 15IRX10` |
| Codec | Realtek ALC257, `HDA:10ec0257,17aa3dcb,00100001` |
| Intel controller | `8086:7A50`, PCI subsystem `17AA:382B` |
| Speaker node | `alsa_output.pci-0000_00_1f.3.analog-stereo` |
| Active port | `analog-output-speaker` |

The PCI subsystem is not the codec subsystem used to choose the NSX.

Checks performed on 2026-09-27:

- All 31 unittest checks passed (the original 19 plus device selection and
  the existing routing cases exercised with Lenovo's identity).
- `make` compiled the Windows host/controller and native Pulse volume reader.
- `makepkg --nodeps --noconfirm` built a package from a temporary archive of
  the working tree, replacing only the release source in the temporary recipe.
  All source and runtime SHA-256 checks passed; package contents contain exactly
  the 25 expected runtime files. The portable innoextract 1.9 already available
  from the OEM investigation was supplied in PATH; dependency checks were
  skipped because it is not registered as an installed system package.
- An isolated Wine prefix using the built package's binaries imported the
  Lenovo device GUID and read back `SUBSYS_17AA3DCB`, all four profiles, Music's
  Lenovo-specific voice setting, and a modified bass parameter. The parameter
  survived stopping Wine completely and reopening the existing configuration.
  No installed service or user settings were changed.
- A 32-second stereo PCM signal at 48 kHz was processed into a file through
  the original SFX/MFX/EFX chain, using the real LOQ endpoint's volume. The
  successful run produced finite, nonzero output. This is a software processing
  check, not audible playback or a measurement of underruns.

The signal check exposed a pre-existing clock problem in `native_volume.hpp`:
Wine's `GetSystemTimeAsFileTime` read 1,779 100-ns ticks (177.9 microseconds)
behind a freshly published native `CLOCK_REALTIME` timestamp. The endpoint,
validity flag and channel count all matched; the strict future-time check
stopped processing. Replacing that clock call with
[`GetSystemTimePreciseAsFileTime`](https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/nf-sysinfoapi-getsystemtimepreciseasfiletime)
allowed the same signal to finish. Timestamp, freshness and identity checks
remain in place. An impulse sent immediately on initialization produced silence;
only the sustained-input result is evidence of nonzero processing.

Run the automated checks from the repository root (Fish compatible):

```fish
rtk proxy env QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME=generic QT_STYLE_OVERRIDE=Fusion python -m unittest discover -s tests -v
rtk proxy make
```

Tests cover exact hardware and speaker-port selection, rejection of unknown
devices, the OEM set and filename delivered to the host, preservation of old
sessions, refusal to reuse another device's settings, and routing/volume policy
for the supported models. Existing UI, translations and native volume ABI checks also run.

## Stabilization: 2026-09-28

The owner requested that tests interrupting audio be prepared for later because
a Discord call was active. Wired headphones and a Bluetooth audio device are
not available. No live volume, mute, profile, route or service changes were made
during this phase; the new source changes still need installation and physical
acceptance.

Small corrections, reusing the existing chain:

- `DesktopAudio` excludes corked (paused) streams from `applications` and
  `active`. Previously a paused player could look like active playback.
- The launcher passes the selected speaker port to `pulse_state`. Its existing
  Pulse subscription now publishes an invalid state and exits if that port
  changes or disappears. The host's existing native-state guard stops processing;
  the Python route check continues to disable the filter and wait for speakers.
  This covers the shared analog sink's speaker/headphone transition without
  adding a routing layer. The exact codec/subsystem match and fixed render target
  remain required, so HDMI, Bluetooth and unrelated USB devices cannot select the
  Lenovo NSX. Physical transition timing remains to be tested.
- The service declares `PartOf` for PipeWire, PipeWire Pulse and WirePlumber.
  Restarting WirePlumber recreates its `filters` metadata; the old Python cached
  enable state would not republish it when the preference had not changed.
  Following the dependency restart rebuilds the existing chain and reapplies the
  saved preference. Unit verification passes; live restart validation is pending.
- `tests/validate_installation.py` now uses the physical endpoint controls,
  accepts `enabled=true, active=false` at idle, preserves profile mode, and checks
  all four profiles' parameter readbacks without writing DSP parameters. It
  restores the initial profile, enable state, volume and mute even after a failed
  check. Active playback or recording prevents the disruptive checks from starting.
  `--snapshot` only reads status, settings and routes.

The downloaded OEM files and `runtime-sha256.json` were not changed during
stabilization. All 25 installed runtime files still match that manifest.

Read-only observation lasted **294.1 seconds**, with 294 service samples and
300 running-node samples from `pw-top`. The same launcher PID stayed ready and
active throughout; systemd reported zero service restarts since startup. The
owner reported **no audible cuts** during this window. The initial `C` rows in
`pw-top` contain zero placeholders and are not a valid baseline; the first `R`
sample already contained the nonzero counters below.

| Node | First running ERR | Last running ERR | Increase |
| --- | ---: | ---: | ---: |
| Physical analog speakers | 5 | 5 | 0 |
| `nahimic_speakers` | 0 | 0 | 0 |
| `nahimic_speakers_capture` | 4 | 4 | 0 |
| `nahimic_speakers_render` | 0 | 0 | 0 |

The origin of the earlier errors is unknown. This short observation used the
existing call, not a controlled music endurance test, and does not establish
zero xruns since boot. No buffer sizes or OEM DSP parameters were adjusted.

| Scenario | Evidence now | Remaining physical check |
| --- | --- | --- |
| Speaker processing / perceived quality | Initial owner confirmation | Windows comparison unavailable; no parity claim |
| Continuous playback / xruns / cuts | 294 s above, no new reported ERR and no cuts heard | At least 30 min of continuous local audio and normal multitasking |
| Volume synchronization / mute | Current endpoint readback; native callback and UI regression tests | Volume changes from both panel and desktop, mute/unmute while listening |
| L/R channels | Both capture and render connections map FL to FL and FR to FR | Listen to separate left/right channel tests |
| Speakers / wired headphones | Both speaker port names accepted; headphone ports rejected and invalidate native state in tests | Pending headphones availability; insert/remove during playback |
| Bluetooth / HDMI | Other targets excluded by device and routing tests; HDMI output visible | Bluetooth unavailable; HDMI switch deferred |
| Suspend / resume | Protocol below prepared | Full sleep/wake cycle with playback recovery |
| PipeWire / WirePlumber restart | Unit verified; dependency restart handling added | Install revision and restart each service separately |
| Logout / login and system reboot | Current boot started a ready service using saved settings | Controlled before/after comparisons and listening |
| Profile / parameter persistence | Installed session reused saved settings; snapshot available | Compare unchanged values across each lifecycle transition |
| Music / Movie / Gaming / Communication | Previous isolated API readbacks; current Gaming readback (139 settings) | Select and listen to all four on the installed revision |
| Repeated bypass / enable | Policy tests for both models; idle validator prepared | Five cycles at idle, then five while listening |

Automated regression checks now cover paused-stream reporting, rejection of
other output targets, invalidation on speaker-port loss, and the installation
validator's idle semantics, DSP preservation, call guard and failure restoration.
These tests use mocks or the real C callback with synthetic Pulse data; they do
not replace plugging in physical devices.

Validation of this revision:

- All **40 unittest checks passed**; `make` and `systemd-analyze --user verify
  packaging/nahimic.service` passed.
- `makepkg --nodeps --noconfirm` built a fresh local-source snapshot using
  temporary [innoextract 1.9](https://constexpr.org/innoextract/) in PATH. As in
  the initial build, dependency checks were skipped only because the portable
  tool is not registered with pacman. No package was installed.
- All source checksums passed. The resulting package contains exactly the 25
  expected runtime files with matching SHA-256 values, and its launcher, routing
  module and systemd unit match the working sources.
- A read-only check of the packaged native reader became ready on the real
  `analog-output-speaker` port and rejected an intentionally different expected
  port. It wrote only temporary state files and changed no audio controls. This
  verifies the query/guard path, not physical headphone insertion.
- `--snapshot` read the current Gaming profile and its 139 parameters from the
  installed service; its device GUID and NSX matched Lenovo. The installed
  launcher stayed at the same PID throughout this phase. Before/after snapshots
  matched for profile, all parameters, enabled state, volume, mute and device.
- All ten documented Fish command blocks passed `fish --no-execute`; the
  disruptive commands were only syntax-checked.

## Local upstream merge: 2026-10-21

Integrated upstream `v0.3.1` (`2460f37`) with the local Lenovo changes. The single
device table now includes MECHREVO P916F (`10ec0256,1d05e004`) alongside Wujie
14X Pro and the LOQ. Both MECHREVO device files use the upstream factory set;
the Lenovo device and all four DS575151 profiles remain in their separate set.
All 25 previous runtime hashes are unchanged; the P916F NSX adds a 26th file.

The launcher adopts upstream's basename-only `--device-file` contract; the host
adds `Devices\\` and rejects path separators. Saved-session identity checks,
speaker-port invalidation, paused-stream reporting and service restart handling
are retained. Upstream's native volume clock fix is also retained: precise time,
two-second maximum state age and 50 ms maximum future skew. No OEM DSP values
were changed.

Validation: **54 unittest checks**, `make`, and a fresh local-source
`makepkg --nodeps --noconfirm` build passed. Portable innoextract 1.9 was used as
before. All source hashes and all 26 runtime hashes in the resulting package
matched; the packaged launcher and systemd unit matched the working sources.
This merge was not installed or tested through live playback. The initial
physical result above remains the hardware evidence; the merged revision still
needs the deferred acceptance checks. No push or PR was performed.

## Deferred physical test procedure (Fish)

Install a package built from this revision when an audio interruption is
acceptable. Use the real speakers as the system output, close calls/recording,
and stop other playback before running the disruptive validator. It cycles the
four profiles, checks real volume/mute, performs five bypass/enable cycles and
restarts **Nahimic only** twice to compare saved parameters and enabled state.
It never writes DSP settings. Results and the original state are saved in the
printed `/tmp/nahimic-install-check-*` directory; copy that directory somewhere
persistent before reboot if needed.

```fish
rtk proxy python tests/validate_installation.py
```

For endurance and acoustic checks, play a local stereo track for at least
30 minutes. Listen for gaps, clicks or changed speed. Capture PipeWire counters
in another terminal, comparing the first **running** sample to the last:

```fish
rtk proxy pw-top -b -n 1801 > ~/nahimic-endurance.txt
```

Use the desktop's speaker channel test to hear left and right separately. During
normal playback, change volume from the Nahimic panel and desktop controls,
mute/unmute from each, select Music/Movie/Gaming/Communication, and repeat five
bypass/enable cycles. Keep EQ and DSP sliders unchanged. Record the original
profile/volume/mute and restore them afterward; check the readbacks below.

For each output transition, keep selecting real physical outputs in the desktop
sound panel. With wired headphones inserted, the speaker filter must stop and
wait for speakers. With Bluetooth or HDMI selected, their streams must bypass
the speaker chain; the Nahimic renderer must never link to those outputs.
Inspect `sink_inputs` in a snapshot: the renderer's sink index must match the
physical analog speaker sink (or be unlinked), while the test player's sink index
matches the selected Bluetooth/HDMI output. Apps explicitly pinned to the real
speakers can still use the speaker filter when another output is the default.
Disconnect or reselect speakers and confirm processing returns. Record separate
results for headphones, Bluetooth and HDMI; unavailable devices remain pending.

Take a read-only snapshot before and after **each** lifecycle transition. Use
different filenames for each pair and wait for `ready=true` before comparing:

```fish
rtk proxy python tests/validate_installation.py --snapshot > ~/nahimic-before.json
rtk proxy nahimic --status
rtk proxy pw-link -l
```

Run one of the following per test, when interruption is acceptable. For logout
and login use the desktop menu. Allow the service to become ready and listen
again before proceeding; space repeated restarts by at least two minutes to
avoid the existing systemd startup rate limit.

| Separate test | Fish command |
| --- | --- |
| WirePlumber restart | `rtk proxy systemctl --user restart wireplumber.service` |
| PipeWire Pulse restart | `rtk proxy systemctl --user restart pipewire-pulse.service` |
| PipeWire restart | `rtk proxy systemctl --user restart pipewire.service` |
| Suspend / resume | `rtk proxy systemctl suspend` |
| System reboot | `rtk proxy systemctl reboot` |

After each transition:

```fish
rtk proxy nahimic --status
rtk proxy python tests/validate_installation.py --snapshot > ~/nahimic-after.json
rtk proxy python -c 'import json,pathlib; p=pathlib.Path.home(); a=json.loads((p/"nahimic-before.json").read_text()); b=json.loads((p/"nahimic-after.json").read_text()); assert a["settings"] is not None and a["settings"]==b["settings"]; assert b["status"]["ready"]; assert a["status"]["enabled"]==b["status"]["enabled"]; assert a["session"]["device_file"]==b["session"]["device_file"]=="17AA3DCB_InternalSpeakers.nsx"; print("profile, parameters, enable state and device preserved")'
rtk proxy journalctl --user -u nahimic.service -b --no-pager
```

`ready` must return to true on speakers. `enabled` records the saved preference;
`active` is true only while an unpaused application passes audio through the
enabled, linked filter. Idle `active=false` is expected. Compare the volume,
mute, device identity and links too, then resume playback and verify sound.
Record any failure with the transition and logs rather than marking the entire
stabilization matrix passed.
