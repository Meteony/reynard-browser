#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "engine/firefox/mobile/ios/app/mobile.js"


def main() -> None:
    old = 'pref("dom.ipc.processPrelaunch.enabled", true);'
    new = 'pref("dom.ipc.processPrelaunch.enabled", false);'

    text = PATH.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"content-process prelaunch pref: expected exactly one anchor in {PATH}, found {count}"
        )

    PATH.write_text(text.replace(old, new, 1))
    print("Content-process prelaunch disabled for startup diagnostic.")


if __name__ == "__main__":
    main()
