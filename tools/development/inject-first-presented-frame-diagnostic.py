#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "engine/firefox/gfx/layers/NativeLayerRootRemoteMacParent.mm"


def replace_once(old: str, new: str, label: str) -> None:
    text = PATH.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"{label}: expected exactly one anchor in {PATH}, found {count}"
        )
    PATH.write_text(text.replace(old, new, 1))


def main() -> None:
    replace_once(
        '#include "mozilla/layers/NativeLayerRootRemoteMacParent.h"\n',
        '''#include "mozilla/layers/NativeLayerRootRemoteMacParent.h"

#ifdef XP_IOS
#  import <Foundation/Foundation.h>
#  import <QuartzCore/CADisplayLink.h>
#  import <QuartzCore/QuartzCore.h>
#  include <dispatch/dispatch.h>
#  include <atomic>
#  include <fcntl.h>
#  include <stdarg.h>
#  include <stdio.h>
#  include <sys/stat.h>
#  include <sys/time.h>
#  include <unistd.h>
#endif
''',
        "presented-frame diagnostic headers",
    )

    replace_once(
        "namespace mozilla {\nnamespace layers {\n",
        '''#ifdef XP_IOS
static void ReynardPresentedFrameDiagnosticLog(const char* format, ...) {
  static const char* kDirectory =
      "/var/mobile/Documents/ReynardDiagnostics";
  static const char* kPath =
      "/var/mobile/Documents/ReynardDiagnostics/startup.log";

  mkdir(kDirectory, 0755);
  int fd = open(kPath, O_WRONLY | O_CREAT | O_APPEND, 0644);
  if (fd < 0) {
    return;
  }

  char message[1024];
  va_list args;
  va_start(args, format);
  vsnprintf(message, sizeof(message), format, args);
  va_end(args);

  timeval tv = {};
  gettimeofday(&tv, nullptr);
  const double wallTime =
      static_cast<double>(tv.tv_sec) + static_cast<double>(tv.tv_usec) / 1e6;

  char line[1400];
  int length = snprintf(
      line, sizeof(line), "native wall=%.6f pid=%d PresentedFrame %s\\n",
      wallTime, getpid(), message);
  if (length > 0) {
    if (length >= static_cast<int>(sizeof(line))) {
      length = static_cast<int>(sizeof(line)) - 1;
    }
    write(fd, line, static_cast<size_t>(length));
  }
  close(fd);
}

static std::atomic<uint64_t> sReynardNativeCommitSequence{0};

@interface ReynardPresentedFrameProbe : NSObject {
 @private
  uint64_t mSequence;
  double mCommitMediaTime;
  double mCandidatePresentationTime;
}
- (instancetype)initWithSequence:(uint64_t)sequence
                 commitMediaTime:(double)commitMediaTime;
- (void)displayLinkFired:(CADisplayLink*)displayLink;
@end

@implementation ReynardPresentedFrameProbe
- (instancetype)initWithSequence:(uint64_t)sequence
                 commitMediaTime:(double)commitMediaTime {
  self = [super init];
  if (self) {
    mSequence = sequence;
    mCommitMediaTime = commitMediaTime;
    mCandidatePresentationTime = 0.0;
  }
  return self;
}

- (void)displayLinkFired:(CADisplayLink*)displayLink {
  if (mCandidatePresentationTime == 0.0) {
    mCandidatePresentationTime = displayLink.targetTimestamp;
    ReynardPresentedFrameDiagnosticLog(
        "critical display-candidate seq=%llu commitMedia=%.6f "
        "timestamp=%.6f target=%.6f deltaMs=%.3f",
        static_cast<unsigned long long>(mSequence), mCommitMediaTime,
        displayLink.timestamp, displayLink.targetTimestamp,
        (displayLink.targetTimestamp - mCommitMediaTime) * 1000.0);
    return;
  }

  ReynardPresentedFrameDiagnosticLog(
      "critical presented-frame-confirmed seq=%llu candidateTarget=%.6f "
      "callbackMedia=%.6f nextTimestamp=%.6f",
      static_cast<unsigned long long>(mSequence), mCandidatePresentationTime,
      CACurrentMediaTime(), displayLink.timestamp);
  [displayLink invalidate];
}
@end

static void ReynardSchedulePresentedFrameProbe(uint64_t aSequence,
                                               double aCommitMediaTime) {
  // Keep the probe bounded so startup tracing cannot turn into frame polling.
  if (aSequence > 24) {
    return;
  }

  dispatch_async(dispatch_get_main_queue(), ^{
    ReynardPresentedFrameProbe* probe =
        [[ReynardPresentedFrameProbe alloc] initWithSequence:aSequence
                                            commitMediaTime:aCommitMediaTime];
    CADisplayLink* displayLink =
        [CADisplayLink displayLinkWithTarget:probe
                                    selector:@selector(displayLinkFired:)];
    [displayLink addToRunLoop:[NSRunLoop mainRunLoop]
                      forMode:NSRunLoopCommonModes];
    [probe release];
  });
}
#endif

namespace mozilla {
namespace layers {
''',
        "presented-frame diagnostic support",
    )

    replace_once(
        '''NativeLayerRootRemoteMacParent::RecvCommitNativeLayerCommands(
    nsTArray<NativeLayerCommand>&& aCommands) {
  for (auto& command : aCommands) {
''',
        '''NativeLayerRootRemoteMacParent::RecvCommitNativeLayerCommands(
    nsTArray<NativeLayerCommand>&& aCommands) {
#ifdef XP_IOS
  size_t changedSurfaceCount = 0;
#endif
  for (auto& command : aCommands) {
''',
        "native layer commit counters",
    )

    replace_once(
        '''      case NativeLayerCommand::TCommandChangedSurface: {
        auto& changedSurface = command.get_CommandChangedSurface();
''',
        '''      case NativeLayerCommand::TCommandChangedSurface: {
        auto& changedSurface = command.get_CommandChangedSurface();
#ifdef XP_IOS
        ++changedSurfaceCount;
#endif
''',
        "changed surface counter",
    )

    replace_once(
        '''  mRealNativeLayerRoot->CommitToScreen();

  return IPC_OK();
''',
        '''#ifdef XP_IOS
  const uint64_t sequence =
      sReynardNativeCommitSequence.fetch_add(1, std::memory_order_relaxed) + 1;
  ReynardPresentedFrameDiagnosticLog(
      "critical native-layer-commit ENTER seq=%llu root=%p commands=%zu "
      "changedSurfaces=%zu media=%.6f",
      static_cast<unsigned long long>(sequence),
      static_cast<void*>(mRealNativeLayerRoot.get()), aCommands.Length(),
      changedSurfaceCount, CACurrentMediaTime());
#endif

  const bool committed = mRealNativeLayerRoot->CommitToScreen();

#ifdef XP_IOS
  const double commitMediaTime = CACurrentMediaTime();
  ReynardPresentedFrameDiagnosticLog(
      "critical native-layer-commit EXIT seq=%llu root=%p committed=%d "
      "changedSurfaces=%zu media=%.6f",
      static_cast<unsigned long long>(sequence),
      static_cast<void*>(mRealNativeLayerRoot.get()), committed ? 1 : 0,
      changedSurfaceCount, commitMediaTime);
  if (committed && changedSurfaceCount > 0) {
    ReynardSchedulePresentedFrameProbe(sequence, commitMediaTime);
  }
#endif

  return IPC_OK();
''',
        "native layer commit probe",
    )

    print("First presented-frame diagnostic injected successfully.")


if __name__ == "__main__":
    main()
