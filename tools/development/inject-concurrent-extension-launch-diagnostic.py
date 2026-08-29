#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "engine/firefox/ipc/glue/NSExtensionUtils.mm"


def main() -> None:
    """Run NSExtension request creation on a concurrent queue for this diagnostic."""
    old = "  dispatch_async(ExtensionLaunchQueue(), ^{\n"
    new = (
        "  // Diagnostic: allow independent extension process launches to overlap.\n"
        "  dispatch_async(dispatch_get_global_queue(QOS_CLASS_DEFAULT, 0), ^{\n"
    )

    text = PATH.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"extension launch queue: expected exactly one anchor in {PATH}, found {count}"
        )

    PATH.write_text(text.replace(old, new, 1))
    print("NSExtension launch queue relaxed for concurrent-start diagnostic.")


if __name__ == "__main__":
    main()
