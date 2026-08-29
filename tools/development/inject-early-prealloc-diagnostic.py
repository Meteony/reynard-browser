#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "engine/firefox/mobile/ios/app/mobile.js"


def main() -> None:
    """Start one iOS content preallocation immediately for this diagnostic."""
    enabled = 'pref("dom.ipc.processPrelaunch.enabled", true);'
    delay = 'pref("dom.ipc.processPrelaunch.delayMs", 0);'
    count = 'pref("dom.ipc.processPrelaunch.fission.number", 1);'

    text = PATH.read_text()
    if text.count(enabled) != 1:
        raise SystemExit(
            f"prelaunch enabled pref: expected exactly one anchor in {PATH}, "
            f"found {text.count(enabled)}"
        )
    if "dom.ipc.processPrelaunch.delayMs" in text:
        raise SystemExit(f"prelaunch delay pref already exists in {PATH}")
    if "dom.ipc.processPrelaunch.fission.number" in text:
        raise SystemExit(f"prelaunch process-count pref already exists in {PATH}")

    replacement = f"{enabled}\n{delay}\n{count}"
    PATH.write_text(text.replace(enabled, replacement, 1))
    print("iOS prelaunch diagnostic configured for delay=0 ms, count=1.")


if __name__ == "__main__":
    main()
