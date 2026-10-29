# Changes

## 0.4.0-rc.1 — reliability and native controls

- Added top-right Power Off and Pause/Resume icons, with accessible names and tooltips.
- Off requests black and zero brightness, stops capture, retains preferences, and
  sends zero again when an enabled device reconnects. It never re-enables a manually
  disconnected device. Acknowledgement means a transport write, not LED state readback.
- Moved mode-specific brightness to a vertical fill slider beside the live preview.
  Mouse, keyboard, and wheel input remain available. Advanced sliders stay horizontal.
- Replaced continuous-settings backlogs with a latest-value mailbox and debounced
  settings writes. Quit flushes the final value.
- Fixed false music silence caused by stereo channel cancellation.
- Added strict, field-by-field settings recovery, recoverable backups, and a saved
  last active mode. Future settings versions are protected from overwrite.
- Added a Retry action for failed device connections without enabling automatic retries.
- Capture failures request zero output and retry with bounded backoff; users can retry
  immediately. Default audio-device changes are checked during Music mode.
- Added detected display choices, bounded persistent local error logs, and device-detail
  redaction in exported diagnostics.
- Added semantic version and content/build IDs in the app, diagnostics, and packages.
- Pinned the Windows build/test environment, aligned local and CI builds, and added
  isolated GUI and OpenRGB helper pipe checks for the packaged EXE.
- Kept panel customization out of this update.

This is a release candidate. Physical BLE/audio and clean-machine acceptance are
separate from the automated checks. See ACCEPTANCE.md.

## 0.3.0 — preserved baseline

Original LumaFlow 0.3 source, before the reliability and controls changes.
Git tag: `v0.3.0`. Commit: `a716c84`.
