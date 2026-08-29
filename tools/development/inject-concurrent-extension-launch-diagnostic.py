#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "engine/firefox/ipc/glue/NSExtensionUtils.mm"


def main() -> None:
    """Run the instrumented NSExtension process-start block concurrently."""
    # inject-startup-trace.py runs before this script and adds the launch-queue
    # marker below. Anchor on that whole block so we only modify the queue used
    # by ExtensionProcess::startWithCompletion, not other legitimate users of
    # ExtensionLaunchQueue() in NSExtensionUtils.mm.
    old = (
        "  void (^completion)(NSError* _Nullable) = [aCompletion copy];\n\n"
        "  dispatch_async(ExtensionLaunchQueue(), ^{\n"
        '    ReynardStartupDiagnosticLog("ExtensionProcess launch queue ENTER");\n'
    )
    new = (
        "  void (^completion)(NSError* _Nullable) = [aCompletion copy];\n\n"
        "  // Diagnostic only: allow independent extension process launches to overlap.\n"
        "  dispatch_async(dispatch_get_global_queue(QOS_CLASS_DEFAULT, 0), ^{\n"
        '    ReynardStartupDiagnosticLog("ExtensionProcess concurrent launch queue ENTER");\n'
    )

    text = PATH.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"instrumented extension start block: expected exactly one anchor in {PATH}, found {count}"
        )

    PATH.write_text(text.replace(old, new, 1))
    print("NSExtension process-start queue relaxed for concurrent-start diagnostic.")


if __name__ == "__main__":
    main()
