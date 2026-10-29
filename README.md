# LumaFlow 0.3

NBBUFF Sync has become **LumaFlow**: a local Windows lighting studio with
mode-specific controls, animated previews, and scene/audio-driven brightness.
Your two NBBUFF bars still display the same color.

## Upgrade and run

1. Quit the old NBBUFF Sync completely from its tray menu. Closing its window
   alone may only hide it. The old and new apps intentionally share an instance
   lock so they cannot compete for the Bluetooth controller.
2. Extract this archive into a new, permanent folder. Run **Start.cmd**.
3. Your v0.2 device list, verified profiles, manual disconnects and preferences
   are imported automatically on first use. The original settings file is left
   untouched. New settings live at `%LOCALAPPDATA%\LumaFlow\settings.json`.
4. Choose a mode in Studio. Only that mode's controls appear below it. They apply
   immediately and are saved automatically.
5. If you used Windows startup, enable it again in the new app's Settings. This
   replaces the old startup destination with LumaFlow's new location. The existing
   registry value name is retained to avoid duplicate startup entries.

This download contains source, assets, and Windows EXE build scripts. It does not
contain a prebuilt Windows EXE. Python 3.13 64-bit is the suggested build/runtime
version. First-time setup requires internet access to install packages.

## The four modes

### Solid color

Pick a preset or custom color and set its brightness. These controls appear only
while Solid is selected. The glowing orb has gentle decorative motion; the lights
remain steady. Pure red, green and blue presets use only that color channel.

### Screen mirror

The monitor-and-bars preview follows the requested LED color and intensity.

| Control | What it changes |
|---|---|
| Sample from / Display | Whole screen or the left/right/top edge of an MSS display |
| Maximum brightness | Ceiling for this mode; separate from the other modes |
| Follow scene brightness | Dark scenes dim the lights, bright scenes raise them |
| Prefer rich colors | Picks the dominant colorful hue instead of mixing it with white |
| Color saturation | Strengthens color, up to 250%; 100% preserves the chosen hue's saturation |
| Scene exposure | Scales the scene-derived brightness; higher is brighter |
| Dark-scene depth | Higher values darken shadows more; lower values lift them |
| Blackout threshold | Sets the scene level below which LEDs receive zero output |
| Ignore movie black bars | Crops contiguous near-black borders before sampling |
| Color transition softness | Smooths hue changes; lower is faster |
| Brightness response | Smooths intensity changes; lower is faster |

Blackout bypasses smoothing completely: the app sends black RGB and zero
brightness. A small wake-up margin prevents on/off flickering near the threshold.
This also applies if automatic brightness is disabled. The default threshold is
3% of the sampled scene's average maximum-channel intensity. It is not a calibrated
measurement of display luminance. Small bright cursors generally will not keep
an otherwise dark screen illuminated.

The new pipeline separates hue from intensity. A dark red scene stays red at a
lower brightness rather than becoming a pale mix. White scenes remain white.
Dominant-color selection can still switch when a different hue becomes dominant;
use transition softness to smooth it, or disable Prefer rich colors to average.

For an initial movie setup: Whole screen, Prefer rich colors on, saturation 150%,
exposure/depth 100%, threshold 3%, black-bar cropping on. Use maximum brightness
to choose how strong you want the room lighting. Existing brightness limits are
migrated from your old settings rather than silently reset.

### Music sync

The 32 spectrum bars are computed from captured audio, not random animation.
Speaker mode captures the default Windows playback device using WASAPI loopback;
Microphone uses the default input. Audio is processed in memory, not recorded.

Loudness drives brightness up to the mode's maximum. Silence below the cutoff
sends exact zero without a smoothing tail. Bass/mids/treble influence RGB color.
Increase Music sensitivity for quiet tracks; decrease it if intensity stays at
maximum. Silence cutoff is a relative control for rejecting low-level noise.
Color softness and brightness response are independent.

Restart Music after changing Windows audio devices. Microphone mode needs Windows
microphone permission for desktop apps. The preview is a signal visualization,
not physical feedback from the LEDs.

### Atmosphere

24 portable effects generated on the PC, shared across enabled compatible devices:

Rainbow flow, Aurora, Ocean drift, Sunset, Neon dreams, Forest glow, Candy clouds,
Northern lights, Ember, Candlelight, Fireplace, Deep space, Lavender mist,
Golden hour, Tropical tide, Ice glow, Rose garden, Cyberpunk, Rainbow breathe,
Blue breathe, Warm breathe, Heartbeat, Police colors, and Color steps.

Each mode has a brightness ceiling. **Cycle duration** controls speed: fewer
seconds is faster. Effects that breathe or shimmer also modulate brightness.
Police colors is a slower red/blue chase, not a rapid strobe. These are whole-light
color effects, not the phone app's firmware animations or per-LED rainbows.

Flowing ribbons take the current requested light color. Settings → Animate previews
can disable decorative motion. Audio spectrum bars still reflect live sound.

## Pause, memory, and connections

Pause stops capture and transmission, leaving the LEDs at their last color.
Its preview shows a paused state. Brightness changes apply when a mode is active.
All four mode brightness limits are remembered separately.

Enabled devices reconnect when the app launches. Manual Disconnect persists
across relaunches. Forget removes a saved device. Temporary failures use bounded
backoff retries, independently per device, so one slow connection cannot stall
all the lights. Disable reconnection in Settings if preferred.

Closing the window hides it to the tray by default. Use the tray menu's Quit to
stop the app. Automatic startup occurs at Windows sign-in for your account.
Starting hidden and resuming the last mode are separate options. Screen/audio
capture resumes only when Resume the last lighting mode is enabled and that
mode was saved. Put the app in its permanent folder before enabling startup.

## Integrations

| Adapter | Support |
|---|---|
| Bluetooth ELK/MELK | Whole-controller RGB on FFF0/FFF3; native brightness for MELK and ELK-BLEDOB; RGB-only fallback |
| Wi-Fi WLED | JSON API at a manually entered local address; all existing active segments follow the shared color |
| OpenRGB | Local SDK server on port 6742; explicitly named, unique device supporting Direct mode |

Your MELK-OA10 bars use the MELK profile. Additional BLE devices require their
own verified protocol. New devices must pass the manual RGB check before normal
sync. Other brands such as Hue, Govee and Tuya are not implemented.

OpenRGB provides an indirect route to supported USB/internal PC lighting; this
app does not control arbitrary USB power cables or motherboard headers directly.
WLED requires WLED firmware, not simply any Wi-Fi bulb. WLED segment effects are
replaced while syncing; reconnect after editing the segment layout.

## Build and share an EXE

On Windows, run **Build-EXE.cmd**. It creates:

- `dist\LumaFlow\LumaFlow.exe`, with the new wave icon.
- `dist\LumaFlow-Windows.zip`, containing the full app folder.

Share that generated ZIP. Recipients do not need Python, but must keep the entire
folder together. The download you are reading now is the source/build package;
its Windows build has not been executed in this Linux development workspace.
A manual GitHub Actions Windows build workflow is included for a repository with
these files at its root. No remote workflow was run.

The icon is an original code-native two-wave mark, matching the preview style.
`make_icon.py` regenerates its PNG and ICO files from the same Qt paths used by
the running app. Keep dependency license files when distributing a built app.

## Limits and troubleshooting

- Physical hue, brightness, blackout response and Windows audio must be verified
  on your hardware. Automated tests cannot prove the controller obeys a command.
- BLE is capped at 10 commands/second. A change to both color and native brightness
  requires two commands and can reduce combined update rate to around 5/second.
  The app uses the latest frame and avoids a stale-frame queue. It is not 60 FPS.
- The preview may update faster than the physical device. It shows requested
  output; no LED state readback is available. Device transports are not frame-locked.
- Both NBBUFF bars mirror each other. No separate zones, individual LEDs or
  guaranteed compatibility with all Bluetooth/Wi-Fi devices.
- MSS screen capture may be inaccurate with HDR, protected video or exclusive
  fullscreen. Try SDR/borderless mode. Display numbers follow MSS, not necessarily
  Windows' labels. Sampling an edge containing dark UI can legitimately dim lights.
- Border cropping is a heuristic. Turn it off if it excludes parts of a dark scene
  that you intended to sample. A vivid-color mode is an artistic choice, not a
  calibrated color reproduction system.
- Use the remote to power on your bars first. Close the phone app to free BLE.
  If native brightness fails, use RGB only and reverify colors. If the hardware
  brightness was previously set to zero, restore it with the remote first.
- No vendor cloud, sign-in, telemetry, audio/video recording, autoupdater or signed
  installer. Diagnostics include local addresses, names and error logs; review
  before sharing. No personal device data is bundled in this project.
- Preview images in `previews/` are explicitly labeled demonstrations using
  simulated input. They are not evidence of a connected light or live microphone.

## Development and tests

`python -m pip install pytest` then `python -m pytest tests -q` from this folder.
Tests cover known packets, physical-blackout command construction, black/dim/white
and primary-color scenes, letterbox cropping, audio intensity/spectrum, per-mode
limits, effects, migration, GUI visibility, reconnection, and local WLED HTTP I/O.
The capture-thread test exercises bright → black → dim input with a simulated
screen source. Hardware acceptance remains separate.

On Windows, check: solid red → screen full red → black → dim blue; then quiet →
loud → silent music. Verify a breathing effect, saved devices, sign-in startup,
and the built EXE before sharing widely.

## References

- MELK protocol: https://github.com/wporter82/lotus-lamp-python/blob/main/docs/PROTOCOL.md
- ELK-BLEDOB: https://github.com/8none1/elk-bledob
- WLED: https://kno.wled.ge/interfaces/json-api/
- OpenRGB: https://openrgb-python.readthedocs.io/en/latest/pages/api.html
- WASAPI: https://github.com/s0d3s/PyAudioWPatch

Original application code: MIT, see LICENSE. Dependencies retain their own licenses.
