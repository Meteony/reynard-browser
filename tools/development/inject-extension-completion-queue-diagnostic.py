#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "engine/firefox/ipc/glue/NSExtensionUtils.mm"


def replace_once(old: str, new: str, label: str) -> None:
    text = PATH.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"{label}: expected exactly one anchor in {PATH}, found {count}"
        )
    PATH.write_text(text.replace(old, new, 1))


def main() -> None:
    """Keep request creation serialized while letting completions resolve independently."""
    launch_queue = '''static dispatch_queue_t ExtensionLaunchQueue() {
  static dispatch_queue_t queue;
  static dispatch_once_t onceToken;
  dispatch_once(&onceToken, ^{
    queue = dispatch_queue_create("com.minh-ton.Reynard.ExtensionLaunchQueue",
                                  DISPATCH_QUEUE_SERIAL);
  });
  return queue;
}
'''
    completion_queue = launch_queue + '''
static dispatch_queue_t ExtensionCompletionQueue() {
  static dispatch_queue_t queue;
  static dispatch_once_t onceToken;
  dispatch_once(&onceToken, ^{
    queue = dispatch_queue_create(
        "com.minh-ton.Reynard.ExtensionCompletionQueue", DISPATCH_QUEUE_SERIAL);
  });
  return queue;
}
'''
    replace_once(
        launch_queue,
        completion_queue,
        "extension completion queue declaration",
    )

    replace_once(
        '''    void (^completeOnce)(NSError* _Nullable) = ^(NSError* _Nullable error) {
      dispatch_async(ExtensionLaunchQueue(), ^{
        if (completed) {
''',
        '''    void (^completeOnce)(NSError* _Nullable) = ^(NSError* _Nullable error) {
      dispatch_async(ExtensionCompletionQueue(), ^{
        ReynardStartupDiagnosticLog("ExtensionProcess completion queue ENTER");
        if (completed) {
''',
        "completeOnce queue",
    )

    print(
        "NSExtension request creation remains serialized; completion delivery uses a separate serial queue."
    )


if __name__ == "__main__":
    main()
