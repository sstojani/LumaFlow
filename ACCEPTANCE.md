# LumaFlow 0.4.0-rc.1 — hardware acceptance

Automated tests and isolated rendering do not verify what the LEDs physically do.
Record the Build ID shown in Diagnostics when reporting results.

## Run the candidate

1. Quit the previous LumaFlow from its tray menu. Closing its window may only hide it.
2. Start `dist\LumaFlow\LumaFlow.exe`, or use `Start.cmd` for the current source.
3. Check that the sidebar shows version `0.4.0-rc.1` and a Build ID.
4. In Devices, confirm your saved controller and brightness profile are correct.
   Keep the phone lighting app closed while testing Bluetooth.

## Observe on the actual bars

- Solid: red, green, blue, white; brightness 0, 25, 50, 100. Drag the vertical control
  quickly, then check that the final level is applied and retained after restart.
- Pause: while lit, press Pause. The bars should hold their color. Press Resume
  and check that the previous mode resumes.
- Power: press Power while lit. Both bars should go dark. Press it again and check
  that the previous mode and brightness return. Pause is disabled while Off is selected.
- Off/reconnect: with Off selected, temporarily power-cycle the controller. After
  Bluetooth reconnects, LumaFlow should send zero output. It cannot control a device
  while that device is unreachable, and it cannot suppress firmware startup effects
  that occur before a connection is established.
- Manual disconnect: Disconnect in Devices, restart LumaFlow, and confirm it stays
  disconnected. Off must not re-enable it.
- Screen: full-screen red, bright scene, black screen, dim blue; repeat with a small
  cursor and letterboxed video. Confirm blackout and subsequent recovery.
- Music: quiet, loud, silence; then change the default Windows playback device.
  Check that capture recovers, or that an actionable source error appears. Test the
  microphone separately if you use it.
- Atmosphere: check a color flow and breathing effect, their speed, and brightness.
- Sleep/wake: check reconnection and capture recovery after Windows resumes.
- Tray/startup: verify hide, reopen, Quit, optional sign-in startup and optional resume.
- Display scaling: check your normal Windows scale and window size. Advanced
  controls may scroll vertically; there should be no clipped horizontal Studio content.
- Leave the app running during a normal session and watch for growing memory use,
  persistent lag, unexplained disconnects, or incorrect source-error messages.

## Distribution checks still requiring a separate machine/account

- Extract the complete versioned ZIP on a Windows machine without Python installed.
- Confirm startup, icons, BLE, and audio behavior with the applicable permissions.
- If used, verify real WLED output and OpenRGB SDK-server output.

## Rollback

The original source is stored on GitHub at tag `v0.3.0`. Prefer a separate checkout
or extracted copy for testing an older version, so current work is preserved.

Before upgrading an existing v0.3 settings file, v0.4 saves
`%LOCALAPPDATA%\LumaFlow\settings-v3.before-v4.json`. To restore old preferences,
quit both versions, preserve the current `settings.json` under another name, and
copy that backup to `settings.json` before starting v0.3. The old app does not
understand the new Off mode. Legacy v0.2 settings are left untouched.

The new source should be pushed after acceptance, as requested. The baseline
has already been pushed; this checklist itself does not claim hardware acceptance.
