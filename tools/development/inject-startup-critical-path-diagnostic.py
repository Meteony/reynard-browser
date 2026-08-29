#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GECKO = ROOT / "engine" / "firefox"
TAB_MANAGER = ROOT / "browser/Reynard/Client/TabManagement/TabManagerImpl.swift"


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    """Replace one exact anchor and fail if the source no longer matches."""
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))


def insert_after(path: Path, anchor: str, addition: str, label: str) -> None:
    """Insert diagnostic code immediately after one exact source anchor."""
    replace_once(path, anchor, anchor + addition, label)


def c_logger(component: str) -> str:
    return f'''\
#ifdef XP_IOS
static void ReynardCriticalPathDiagnosticLog(const char* format, ...) {{
  static const char* kDirectory =
      "/var/mobile/Documents/ReynardDiagnostics";
  static const char* kPath =
      "/var/mobile/Documents/ReynardDiagnostics/startup.log";

  mkdir(kDirectory, 0755);
  int fd = open(kPath, O_WRONLY | O_CREAT | O_APPEND, 0644);
  if (fd < 0) {{
    return;
  }}

  char message[1024];
  va_list args;
  va_start(args, format);
  vsnprintf(message, sizeof(message), format, args);
  va_end(args);

  timeval tv = {{}};
  gettimeofday(&tv, nullptr);
  const double wallTime =
      static_cast<double>(tv.tv_sec) + static_cast<double>(tv.tv_usec) / 1e6;

  char line[1400];
  int length = snprintf(line, sizeof(line),
                        "native wall=%.6f pid=%d {component} %s\\n", wallTime,
                        getpid(), message);
  if (length > 0) {{
    if (length >= static_cast<int>(sizeof(line))) {{
      length = static_cast<int>(sizeof(line)) - 1;
    }}
    write(fd, line, static_cast<size_t>(length));
  }}
  close(fd);
}}
#endif
'''


def inject_tab_critical_path() -> None:
    insert_after(
        TAB_MANAGER,
        "    private func loadURL(_ url: String, in tab: Tab) {\n",
        '        GeckoStartupDiagnostic.log("critical loadURL tabID=\\(tab.id) selected=\\(selectedTab?.session === tab.session ? 1 : 0)")\n',
        "loadURL marker",
    )

    replace_once(
        TAB_MANAGER,
        """        tab.state.restoreState = .none
        tab.state.suppressInitialNavigation = false
        loadURL(url, in: tab)
""",
        """        tab.state.restoreState = .none
        tab.state.suppressInitialNavigation = false
        GeckoStartupDiagnostic.log(
            "critical restored-load-request tabID=\\(tab.id) selected=\\(selectedTab?.session === tab.session ? 1 : 0)"
        )
        loadURL(url, in: tab)
""",
        "restored load request marker",
    )

    insert_after(
        TAB_MANAGER,
        "        let selectedTab = tabs(for: mode)[index]\n",
        '        GeckoStartupDiagnostic.log("critical selected-tab tabID=\\(selectedTab.id) mode=\\(mode) index=\\(index) sessionOpen=\\(selectedTab.session.isOpen() ? 1 : 0)")\n',
        "selected tab marker",
    )

    insert_after(
        TAB_MANAGER,
        "    func onFirstComposite(session: GeckoSession) {\n",
        '        GeckoStartupDiagnostic.log("critical first-composite selected=\\(selectedTab?.session === session ? 1 : 0)")\n',
        "first composite marker",
    )

    replace_once(
        TAB_MANAGER,
        "    func onFirstContentfulPaint(session: GeckoSession) {}\n",
        """    func onFirstContentfulPaint(session: GeckoSession) {
        GeckoStartupDiagnostic.log(
            "critical first-contentful-paint selected=\\(selectedTab?.session === session ? 1 : 0)"
        )
    }
""",
        "first contentful paint marker",
    )

    insert_after(
        TAB_MANAGER,
        "    func onPageStart(session: GeckoSession, url: String) {\n",
        '        GeckoStartupDiagnostic.log("critical page-start selected=\\(selectedTab?.session === session ? 1 : 0)")\n',
        "page start marker",
    )

    insert_after(
        TAB_MANAGER,
        "    func onPageStop(session: GeckoSession, success: Bool) {\n",
        '        GeckoStartupDiagnostic.log("critical page-stop selected=\\(selectedTab?.session === session ? 1 : 0) success=\\(success ? 1 : 0)")\n',
        "page stop marker",
    )

    insert_after(
        TAB_MANAGER,
        "    func onLocationChange(session: GeckoSession, url: String?, permissions: [ContentPermission]) {\n",
        '        GeckoStartupDiagnostic.log("critical location-change selected=\\(selectedTab?.session === session ? 1 : 0) hasURL=\\(url == nil ? 0 : 1)")\n',
        "location change marker",
    )


def inject_content_remote_type() -> None:
    path = GECKO / "dom/ipc/ContentParent.cpp"
    text = path.read_text()
    headers = (
        "#include <fcntl.h>\n",
        "#include <stdarg.h>\n",
        "#include <stdio.h>\n",
        "#include <sys/stat.h>\n",
        "#include <sys/time.h>\n",
        "#include <unistd.h>\n",
    )
    additions = "".join(header for header in headers if header not in text)
    if additions:
        insert_after(
            path,
            '#include "ContentParent.h"\n',
            "\n" + additions,
            "ContentParent diagnostic headers",
        )

    replace_once(
        path,
        'namespace dom {\n\nLazyLogModule gProcessLog("Process");\n',
        'namespace dom {\n\n' + c_logger("ContentParent") + 'LazyLogModule gProcessLog("Process");\n',
        "ContentParent logger",
    )

    replace_once(
        path,
        """  mLaunchYieldTS = TimeStamp::Now();
  return mSubprocess->AsyncLaunch(std::move(extraArgs));
""",
        """#ifdef XP_IOS
  ReynardCriticalPathDiagnosticLog(
      "launch childID=%d remoteType=%s preallocBlocker=%d isForBrowser=%d",
      int(mSubprocess->GetChildID()), mRemoteType.get(),
      mIsAPreallocBlocker ? 1 : 0, mIsForBrowser ? 1 : 0);
#endif
  mLaunchYieldTS = TimeStamp::Now();
  return mSubprocess->AsyncLaunch(std::move(extraArgs));
""",
        "ContentParent launch marker",
    )

    insert_after(
        path,
        "/*static*/ UniqueContentParentKeepAlive ContentParent::MakePreallocProcess() {\n",
        '#ifdef XP_IOS\n  ReynardCriticalPathDiagnosticLog("launch-reason prealloc-request");\n#endif\n',
        "prealloc request marker",
    )

    insert_after(
        path,
        "    preallocated->mRemoteType.Assign(aRemoteType);\n",
        '#ifdef XP_IOS\n    ReynardCriticalPathDiagnosticLog("launch-reason prealloc-specialize remoteType=%s", PromiseFlatCString(aRemoteType).get());\n#endif\n',
        "prealloc specialize marker",
    )

    child_host = GECKO / "ipc/glue/GeckoChildProcessHost.cpp"
    replace_once(
        child_host,
        '  ReynardStartupDiagnosticLog("IosProcessLauncher::DoLaunch ENTER type=%d", int(mProcessType));\n',
        '  ReynardStartupDiagnosticLog("IosProcessLauncher::DoLaunch ENTER type=%d childID=%d", int(mProcessType), int(mChildID));\n',
        "child host launch child ID marker",
    )


def main() -> None:
    inject_tab_critical_path()
    inject_content_remote_type()
    print("Startup critical-path diagnostic injected successfully.")


if __name__ == "__main__":
    main()
