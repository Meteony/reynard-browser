#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GECKO = ROOT / "engine" / "firefox"


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))


def insert_after(path: Path, anchor: str, addition: str, label: str) -> None:
    replace_once(path, anchor, anchor + addition, label)


def c_logger(component: str) -> str:
    return f'''
static void ReynardStartupDiagnosticLog(const char* format, ...) {{
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
'''


def inject_swift() -> None:
    jit = ROOT / "browser/Reynard/JIT/JITController.swift"
    replace_once(
        jit,
        "private let diagnosticBypassJIT = true",
        "private let diagnosticBypassJIT = false",
        "disable old JIT bypass",
    )

    session = ROOT / "browser/GeckoView/Session/GeckoSession.swift"
    insert_after(
        session,
        "    public func open(windowId: String? = nil) {\n",
        '        GeckoStartupDiagnostic.log("GeckoSession.open ENTER")\n',
        "GeckoSession open entry",
    )
    replace_once(
        session,
        "        window = GeckoViewOpenWindow(\n",
        '        GeckoStartupDiagnostic.log("GeckoSession.open before GeckoViewOpenWindow")\n'
        "        window = GeckoViewOpenWindow(\n",
        "GeckoSession before GeckoViewOpenWindow",
    )
    replace_once(
        session,
        "        guard let engineView = window?.view() else {\n",
        '        GeckoStartupDiagnostic.log("GeckoSession.open after GeckoViewOpenWindow")\n'
        "        guard let engineView = window?.view() else {\n",
        "GeckoSession after GeckoViewOpenWindow",
    )
    insert_after(
        session,
        "        autofillHandler.attach(to: engineView)\n",
        '        GeckoStartupDiagnostic.log("GeckoSession.open EXIT")\n',
        "GeckoSession open exit",
    )


def inject_nsextension() -> None:
    path = GECKO / "ipc/glue/NSExtensionUtils.mm"
    text = path.read_text()
    headers = (
        "#include <fcntl.h>\n",
        "#include <stdarg.h>\n",
        "#include <stdio.h>\n",
        "#include <sys/stat.h>\n",
        "#include <sys/time.h>\n",
        "#include <unistd.h>\n",
    )
    additions = "".join(h for h in headers if h not in text)
    if additions:
        insert_after(
            path,
            "#import <Foundation/Foundation.h>\n",
            additions,
            "NSExtension diagnostic headers",
        )

    insert_after(path, "using namespace mozilla::widget;\n", c_logger("NSExtension"), "NSExtension logger")
    insert_after(
        path,
        "- (BOOL)listener:(NSXPCListener*)listener\n"
        "    shouldAcceptNewConnection:(NSXPCConnection*)newConnection {\n",
        '  ReynardStartupDiagnosticLog("NSXPC listener shouldAcceptNewConnection ENTER");\n',
        "NSXPC accept enter",
    )
    insert_after(
        path,
        "  [newConnection resume];\n",
        '  ReynardStartupDiagnosticLog("NSXPC listener shouldAcceptNewConnection EXIT");\n',
        "NSXPC accept exit",
    )
    insert_after(path, "- (void)ping {\n", '  ReynardStartupDiagnosticLog("bootstrap ping received");\n', "bootstrap ping")
    insert_after(
        path,
        "- (void)startWithCompletion:\n"
        "    (void (^_Nonnull)(NSError* _Nullable error))aCompletion {\n",
        '  ReynardStartupDiagnosticLog("ExtensionProcess startWithCompletion CALL");\n',
        "ExtensionProcess start",
    )
    replace_once(
        path,
        "  void (^completion)(NSError* _Nullable) = [aCompletion copy];\n\n"
        "  dispatch_async(ExtensionLaunchQueue(), ^{\n",
        "  void (^completion)(NSError* _Nullable) = [aCompletion copy];\n\n"
        "  dispatch_async(ExtensionLaunchQueue(), ^{\n"
        '    ReynardStartupDiagnosticLog("ExtensionProcess launch queue ENTER");\n',
        "ExtensionProcess launch queue",
    )
    insert_after(
        path,
        "        completed = true;\n",
        '        ReynardStartupDiagnosticLog("ExtensionProcess completeOnce error=%s",\n'
        '                                    error ? "yes" : "no");\n',
        "ExtensionProcess completion",
    )
    insert_after(
        path,
        "    [mListenerDelegate setConnectionHandler:^(NSXPCConnection* connection) {\n",
        '      ReynardStartupDiagnosticLog("ExtensionProcess connectionHandler ENTER");\n',
        "ExtensionProcess connection handler enter",
    )
    insert_after(
        path,
        "      if (!process->mLibXPCConnection) {\n"
        "        completeOnce(ExtensionLaunchError(\n"
        '            @"Failed to get libxpc connection from NSXPCConnection"));\n'
        "        return;\n"
        "      }\n",
        '      ReynardStartupDiagnosticLog("ExtensionProcess connectionHandler EXIT libxpc=ready");\n',
        "ExtensionProcess connection handler exit",
    )
    insert_after(
        path,
        "    NSError* extensionError = nil;\n",
        '    ReynardStartupDiagnosticLog("before NSExtension extensionWithIdentifier");\n',
        "before extensionWithIdentifier",
    )
    insert_after(
        path,
        "    mExtension = [[NSExtension extensionWithIdentifier:extensionIdentifier\n"
        "                                                 error:&extensionError] retain];\n",
        '    ReynardStartupDiagnosticLog("after NSExtension extensionWithIdentifier success=%d",\n'
        "                                mExtension != nil);\n",
        "after extensionWithIdentifier",
    )
    insert_after(
        path,
        "    NSError* requestError = nil;\n",
        '    ReynardStartupDiagnosticLog("before beginExtensionRequestWithInputItems");\n',
        "before beginExtensionRequest",
    )
    insert_after(
        path,
        "    mRequestIdentifier =\n"
        "        [[mExtension beginExtensionRequestWithInputItems:@[ input ]\n"
        "                                                   error:&requestError] retain];\n",
        '    ReynardStartupDiagnosticLog("after beginExtensionRequestWithInputItems request=%s",\n'
        '                                mRequestIdentifier ? "created" : "nil");\n',
        "after beginExtensionRequest",
    )
    insert_after(
        path,
        "void NSExtensionProcess::StartProcess(\n"
        "    const std::function<void(Result<NSExtensionProcess, LaunchError>&&)>&\n"
        "        aCompletion) {\n",
        '  ReynardStartupDiagnosticLog("NSExtensionProcess::StartProcess ENTER");\n',
        "NSExtensionProcess StartProcess",
    )
    insert_after(
        path,
        "  [process startWithCompletion:^(NSError* error) {\n",
        '    ReynardStartupDiagnosticLog("NSExtensionProcess::StartProcess completion error=%s",\n'
        '                                error ? "yes" : "no");\n',
        "NSExtensionProcess completion",
    )


def inject_child_host() -> None:
    path = GECKO / "ipc/glue/GeckoChildProcessHost.cpp"
    text = path.read_text()
    headers = (
        "#  include <fcntl.h>\n",
        "#  include <stdarg.h>\n",
        "#  include <sys/stat.h>\n",
        "#  include <sys/time.h>\n",
    )
    additions = "".join(h for h in headers if h not in text)
    if additions:
        replace_once(
            path,
            "#ifdef XP_IOS\n#  include <unistd.h>\n",
            "#ifdef XP_IOS\n" + additions + "#  include <unistd.h>\n",
            "ChildHost diagnostic headers",
        )

    insert_after(
        path,
        "static std::unordered_map<int32_t, UniqueFileHandle> sChildJITPipeWriters;\n",
        c_logger("ChildHost"),
        "ChildHost logger",
    )
    insert_after(
        path,
        "RefPtr<ProcessLaunchPromise> IosProcessLauncher::DoLaunch() {\n",
        '  ReynardStartupDiagnosticLog("IosProcessLauncher::DoLaunch ENTER type=%d", int(mProcessType));\n',
        "DoLaunch enter",
    )
    insert_after(
        path,
        "  auto didSettle = std::make_shared<std::atomic<bool>>(false);\n",
        '  ReynardStartupDiagnosticLog("before NSExtensionProcess::StartProcess type=%d", int(mProcessType));\n',
        "before NSExtensionProcess StartProcess",
    )
    insert_after(
        path,
        "                                       Result<NSExtensionProcess, LaunchError>&&\n"
        "                                           result) {\n",
        '    ReynardStartupDiagnosticLog("NSExtensionProcess::StartProcess callback type=%d error=%d",\n'
        "                                int(self->mProcessType), result.isErr());\n",
        "NSExtensionProcess callback",
    )
    insert_after(
        path,
        "    // Send our bootstrap message to the content and wait for it to reply with\n"
        "    // the task port before resolving.\n",
        '    ReynardStartupDiagnosticLog("before xpc bootstrap send type=%d", int(self->mProcessType));\n',
        "before xpc bootstrap",
    )
    insert_after(
        path,
        "    xpc_connection_send_message_with_reply(\n"
        "        self->mResults.mXPCConnection.get(), bootstrapMessage.get(), nullptr,\n"
        "        ^(xpc_object_t reply) {\n",
        '          ReynardStartupDiagnosticLog("xpc bootstrap reply ENTER type=%d", int(self->mProcessType));\n',
        "xpc bootstrap reply",
    )
    insert_after(
        path,
        "          pid_t pid =\n"
        '              static_cast<pid_t>(xpc_dictionary_get_int64(reply, "pid"));\n',
        '          ReynardStartupDiagnosticLog("xpc bootstrap pid=%d type=%d",\n'
        "                                      int(pid), int(self->mProcessType));\n",
        "xpc bootstrap pid",
    )
    insert_after(
        path,
        "          // Notify child process start\n",
        '          ReynardStartupDiagnosticLog("before NotifyChildProcessStarted pid=%d", int(pid));\n',
        "before child notify",
    )
    insert_after(
        path,
        "          mozilla::widget::NotifyChildProcessStarted(static_cast<int32_t>(pid),\n"
        "                                                     processType);\n",
        '          ReynardStartupDiagnosticLog("after NotifyChildProcessStarted pid=%d", int(pid));\n',
        "after child notify",
    )
    replace_once(
        path,
        "          self->mResults.mHandle = pid;\n"
        "          if (!settleState->exchange(true, std::memory_order_relaxed)) {\n",
        "          self->mResults.mHandle = pid;\n"
        "          if (!settleState->exchange(true, std::memory_order_relaxed)) {\n"
        '            ReynardStartupDiagnosticLog("resolving ProcessLaunchPromise pid=%d", int(pid));\n',
        "resolve process launch promise",
    )


def inject_nswindow() -> None:
    path = GECKO / "widget/uikit/nsWindow.mm"
    text = path.read_text()
    headers = (
        "#include <fcntl.h>\n",
        "#include <stdarg.h>\n",
        "#include <sys/stat.h>\n",
        "#include <sys/time.h>\n",
        "#include <unistd.h>\n",
    )
    additions = "".join(h for h in headers if h not in text)
    if additions:
        insert_after(
            path,
            "#import <UIKit/UIWindow.h>\n",
            "\n" + additions,
            "nsWindow diagnostic headers",
        )

    insert_after(path, "using namespace mozilla::widget;\n", c_logger("nsWindow"), "nsWindow logger")
    insert_after(
        path,
        "void nsWindow::GetCompositorWidgetInitData(\n"
        "    mozilla::widget::CompositorWidgetInitData* aInitData) {\n",
        '  ReynardStartupDiagnosticLog("GetCompositorWidgetInitData ENTER");\n',
        "compositor init enter",
    )
    replace_once(
        path,
        "  MOZ_ASSERT(CompositorThread());\n\n"
        '  Monitor monitor("nsWindow::GetCompositorWidgetInitData");\n',
        "  MOZ_ASSERT(CompositorThread());\n"
        '  ReynardStartupDiagnosticLog("GetCompositorWidgetInitData before compositor Dispatch");\n\n'
        '  Monitor monitor("nsWindow::GetCompositorWidgetInitData");\n',
        "before compositor dispatch",
    )
    replace_once(
        path,
        "  {\n"
        "    MonitorAutoLock lock(monitor);\n"
        "    while (!didBindParentEndpoint) {\n"
        "      lock.Wait();\n"
        "    }\n"
        "  }\n",
        '  ReynardStartupDiagnosticLog("GetCompositorWidgetInitData before monitor wait");\n'
        "  {\n"
        "    MonitorAutoLock lock(monitor);\n"
        "    while (!didBindParentEndpoint) {\n"
        "      lock.Wait();\n"
        "    }\n"
        "  }\n"
        '  ReynardStartupDiagnosticLog("GetCompositorWidgetInitData after monitor wait");\n',
        "compositor monitor wait",
    )
    insert_after(
        path,
        "                                        bool aPrivateMode) {\n"
        "  MOZ_ASSERT(NS_IsMainThread());\n",
        '  ReynardStartupDiagnosticLog("GeckoViewOpenWindow ENTER");\n',
        "GeckoViewOpenWindow enter",
    )
    insert_after(
        path,
        "  nsCOMPtr<mozIDOMWindowProxy> domWindow;\n",
        '  ReynardStartupDiagnosticLog("GeckoViewOpenWindow before nsIWindowWatcher::OpenWindow");\n',
        "before OpenWindow",
    )
    insert_after(
        path,
        "      chromeFlags, iosView, getter_AddRefs(domWindow));\n",
        '  ReynardStartupDiagnosticLog("GeckoViewOpenWindow after nsIWindowWatcher::OpenWindow");\n',
        "after OpenWindow",
    )
    insert_after(
        path,
        "  gvWindow->mWindow = window;\n",
        '  ReynardStartupDiagnosticLog("GeckoViewOpenWindow EXIT");\n',
        "GeckoViewOpenWindow exit",
    )


def main() -> None:
    inject_swift()
    inject_nsextension()
    inject_child_host()
    inject_nswindow()
    print("Startup trace instrumentation injected successfully.")


if __name__ == "__main__":
    main()
