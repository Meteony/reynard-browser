#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REMOTE_PATH = ROOT / "engine/firefox/gfx/layers/NativeLayerRootRemoteMacParent.mm"
CA_PATH = ROOT / "engine/firefox/gfx/layers/NativeLayerCA.mm"


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"{label}: expected exactly one anchor in {path}, found {count}"
        )
    path.write_text(text.replace(old, new, 1))


def inject_remote_surface_arrival_probe() -> None:
    replace_once(
        REMOTE_PATH,
        '#include "mozilla/layers/NativeLayerRootRemoteMacParent.h"\n',
        '''#include "mozilla/layers/NativeLayerRootRemoteMacParent.h"

#ifdef XP_IOS
#  import <QuartzCore/QuartzCore.h>
#  include <atomic>
#  include <fcntl.h>
#  include <stdarg.h>
#  include <stdio.h>
#  include <sys/stat.h>
#  include <sys/time.h>
#  include <unistd.h>
#endif
''',
        "remote surface diagnostic headers",
    )

    replace_once(
        REMOTE_PATH,
        "namespace mozilla {\nnamespace layers {\n",
        '''#ifdef XP_IOS
static void ReynardSurfaceArrivalDiagnosticLog(const char* format, ...) {
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

static std::atomic<uint64_t> sReynardRemoteCommitSequence{0};
#endif

namespace mozilla {
namespace layers {
''',
        "remote surface diagnostic support",
    )

    replace_once(
        REMOTE_PATH,
        '''NativeLayerRootRemoteMacParent::RecvCommitNativeLayerCommands(
    nsTArray<NativeLayerCommand>&& aCommands) {
  if (!mRealNativeLayerRoot) {
    return IPC_OK();
  }

  for (auto& command : aCommands) {
''',
        '''NativeLayerRootRemoteMacParent::RecvCommitNativeLayerCommands(
    nsTArray<NativeLayerCommand>&& aCommands) {
  if (!mRealNativeLayerRoot) {
    return IPC_OK();
  }

#ifdef XP_IOS
  size_t changedSurfaceCount = 0;
#endif
  for (auto& command : aCommands) {
''',
        "remote native layer counters",
    )

    replace_once(
        REMOTE_PATH,
        '''      case NativeLayerCommand::TCommandChangedSurface: {
        auto& changedSurface = command.get_CommandChangedSurface();
''',
        '''      case NativeLayerCommand::TCommandChangedSurface: {
        auto& changedSurface = command.get_CommandChangedSurface();
#ifdef XP_IOS
        ++changedSurfaceCount;
#endif
''',
        "remote changed surface counter",
    )

    replace_once(
        REMOTE_PATH,
        '''  mRealNativeLayerRoot->CommitToScreen();

  return IPC_OK();
''',
        '''#ifdef XP_IOS
  const uint64_t sequence =
      sReynardRemoteCommitSequence.fetch_add(1, std::memory_order_relaxed) + 1;
  if (sequence <= 24) {
    ReynardSurfaceArrivalDiagnosticLog(
        "critical surface-arrival ENTER seq=%llu root=%p commands=%zu "
        "changedSurfaces=%zu media=%.6f",
        static_cast<unsigned long long>(sequence),
        static_cast<void*>(mRealNativeLayerRoot.get()), aCommands.Length(),
        changedSurfaceCount, CACurrentMediaTime());
  }
#endif

  const bool committed = mRealNativeLayerRoot->CommitToScreen();

#ifdef XP_IOS
  if (sequence <= 24) {
    ReynardSurfaceArrivalDiagnosticLog(
        "critical surface-arrival EXIT seq=%llu root=%p committed=%d "
        "changedSurfaces=%zu media=%.6f",
        static_cast<unsigned long long>(sequence),
        static_cast<void*>(mRealNativeLayerRoot.get()), committed ? 1 : 0,
        changedSurfaceCount, CACurrentMediaTime());
  }
#endif

  return IPC_OK();
''',
        "remote surface arrival probe",
    )


def inject_actual_ca_commit_probe() -> None:
    replace_once(
        CA_PATH,
        '#import <QuartzCore/QuartzCore.h>\n',
        '''#import <QuartzCore/QuartzCore.h>

#ifdef XP_IOS
#  import <Foundation/Foundation.h>
#  import <QuartzCore/CADisplayLink.h>
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
        "actual CA commit diagnostic headers",
    )

    replace_once(
        CA_PATH,
        "namespace mozilla {\nnamespace layers {\n",
        '''#ifdef XP_IOS
static void ReynardActualPresentationDiagnosticLog(const char* format, ...) {
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

static std::atomic<uint64_t> sReynardActualCommitSequence{0};

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
    ReynardActualPresentationDiagnosticLog(
        "critical display-candidate seq=%llu commitMedia=%.6f "
        "timestamp=%.6f target=%.6f deltaMs=%.3f",
        static_cast<unsigned long long>(mSequence), mCommitMediaTime,
        displayLink.timestamp, displayLink.targetTimestamp,
        (displayLink.targetTimestamp - mCommitMediaTime) * 1000.0);
    return;
  }

  ReynardActualPresentationDiagnosticLog(
      "critical presented-frame-confirmed seq=%llu candidateTarget=%.6f "
      "callbackMedia=%.6f nextTimestamp=%.6f",
      static_cast<unsigned long long>(mSequence), mCandidatePresentationTime,
      CACurrentMediaTime(), displayLink.timestamp);
  [displayLink invalidate];
}
@end

static void ReynardSchedulePresentedFrameProbe(uint64_t aSequence,
                                               double aCommitMediaTime) {
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
        "actual CA commit diagnostic support",
    )

    replace_once(
        CA_PATH,
        '''  if (!NS_IsMainThread() && mOffMainThreadCommitsSuspended) {
    mCommitPending = true;
    return false;
  }

  CommitRepresentation(WhichRepresentation::ONSCREEN, mOnscreenRootCALayer,
                       mSublayers, mMutatedOnscreenLayerStructure,
                       mWindowIsFullscreen);
''',
        '''  if (!NS_IsMainThread() && mOffMainThreadCommitsSuspended) {
    mCommitPending = true;
    return false;
  }

#ifdef XP_IOS
  const auto diagnosticUpdateRequired = GetMaxUpdateRequired(
      WhichRepresentation::ONSCREEN, mSublayers,
      mMutatedOnscreenLayerStructure);
  const bool diagnosticHasUpdate =
      diagnosticUpdateRequired != NativeLayerCA::UpdateType::None;
#endif

  CommitRepresentation(WhichRepresentation::ONSCREEN, mOnscreenRootCALayer,
                       mSublayers, mMutatedOnscreenLayerStructure,
                       mWindowIsFullscreen);
''',
        "actual CA commit pending-update check",
    )

    replace_once(
        CA_PATH,
        '''  mMutatedOnscreenLayerStructure = false;

  mCommitPending = false;
''',
        '''  mMutatedOnscreenLayerStructure = false;

#ifdef XP_IOS
  if (diagnosticHasUpdate) {
    const uint64_t sequence =
        sReynardActualCommitSequence.fetch_add(1, std::memory_order_relaxed) + 1;
    if (sequence <= 24) {
      const double commitMediaTime = CACurrentMediaTime();
      ReynardActualPresentationDiagnosticLog(
          "critical actual-ca-commit seq=%llu root=%p main=%d update=%d "
          "media=%.6f",
          static_cast<unsigned long long>(sequence), static_cast<void*>(this),
          NS_IsMainThread() ? 1 : 0,
          static_cast<int>(diagnosticUpdateRequired), commitMediaTime);
      ReynardSchedulePresentedFrameProbe(sequence, commitMediaTime);
    }
  }
#endif

  mCommitPending = false;
''',
        "actual CA commit presentation probe",
    )


def main() -> None:
    inject_remote_surface_arrival_probe()
    inject_actual_ca_commit_probe()
    print("First presented-frame diagnostic injected successfully.")


if __name__ == "__main__":
    main()
