//
//  GeckoRuntime.swift
//  Reynard
//
//  Created by Minh Ton on 1/2/26.
//

import Darwin
import Foundation
import UIKit

public enum GeckoStartupDiagnostic {
    public static let directoryPath = "/var/mobile/Documents/ReynardDiagnostics"
    public static let logPath = directoryPath + "/startup.log"

    private static let writeLock = NSLock()

    public static func reset() {
        try? FileManager.default.createDirectory(
            atPath: directoryPath,
            withIntermediateDirectories: true
        )
        try? FileManager.default.removeItem(atPath: logPath)
        log("=== Reynard startup diagnostic launch ===")
    }

    public static func log(_ message: String) {
        let uptime = ProcessInfo.processInfo.systemUptime
        let wallTime = Date().timeIntervalSince1970
        let mainThread = Thread.isMainThread ? 1 : 0
        let line = String(
            format: "%.6f wall=%.6f pid=%d main=%d %@\n",
            uptime,
            wallTime,
            getpid(),
            mainThread,
            message
        )

        guard let data = line.data(using: .utf8) else {
            return
        }

        writeLock.lock()
        defer { writeLock.unlock() }

        try? FileManager.default.createDirectory(
            atPath: directoryPath,
            withIntermediateDirectories: true
        )

        logPath.withCString { path in
            let fd = Darwin.open(
                path,
                O_WRONLY | O_CREAT | O_APPEND,
                mode_t(0o644)
            )
            guard fd >= 0 else {
                return
            }
            defer { Darwin.close(fd) }

            data.withUnsafeBytes { bytes in
                guard let baseAddress = bytes.baseAddress else {
                    return
                }
                _ = Darwin.write(fd, baseAddress, bytes.count)
            }
        }
    }
}

public protocol GeckoScreenOrientationDelegate: AnyObject {
    func lockScreenOrientation(
        to requestedOrientations: UIInterfaceOrientationMask,
        completion: @escaping (GeckoOrientationLockResult) -> Void
    )
    func unlockScreenOrientation()
}

public final class GeckoScreenOrientationController {
    public weak var delegate: GeckoScreenOrientationDelegate?
}

class GeckoRuntimeImpl: NSObject, SwiftGeckoViewRuntime {
    func runtimeDispatcher() -> any SwiftEventDispatcher {
        return GeckoEventDispatcherWrapper.runtimeInstance
    }
    
    func dispatcher(byName name: UnsafePointer<CChar>!) -> any SwiftEventDispatcher {
        return GeckoEventDispatcherWrapper.lookup(byName: String(cString: name))
    }
    
    @objc(childProcessDidStartWithPID:processType:)
    func childProcessDidStart(withPID pid: Int32, processType: String) {
        GeckoStartupDiagnostic.log(
            "parent childProcessDidStart ENTER childPid=\(pid) type=\(processType)"
        )

        // Update jetsam limit for the child process
        updateJetsamControl(pid)
        GeckoStartupDiagnostic.log(
            "parent childProcessDidStart AFTER updateJetsamControl childPid=\(pid) type=\(processType)"
        )
        
        NotificationCenter.default.post(
            name: Notification.Name("GeckoRuntime.ChildProcessDidStart"),
            object: nil,
            userInfo: [
                "pid": NSNumber(value: pid),
                "processType": processType
            ]
        )
        GeckoStartupDiagnostic.log(
            "parent childProcessDidStart EXIT childPid=\(pid) type=\(processType)"
        )
    }
    
    func lockScreenOrientation(
        _ orientationMask: UInt,
        completion: @escaping (GeckoOrientationLockResult) -> Void
    ) {
        let requestedOrientations = UIInterfaceOrientationMask(rawValue: orientationMask)
        DispatchQueue.main.async {
            guard let delegate = GeckoRuntime.orientationController.delegate else {
                completion(.notSupported)
                return
            }
            delegate.lockScreenOrientation(
                to: requestedOrientations,
                completion: completion
            )
        }
    }
    
    func unlockScreenOrientation() {
        DispatchQueue.main.async {
            GeckoRuntime.orientationController.delegate?.unlockScreenOrientation()
        }
    }
}

public class GeckoRuntime {
    static let runtime = GeckoRuntimeImpl()
    public static let orientationController = GeckoScreenOrientationController()
    
    public static var version: String {
        return GeckoRuntimeBridge.version()
    }
    
    public static func setLocale(acceptLanguages: String) {
        GeckoEventDispatcherWrapper.runtimeInstance.dispatch(
            type: "GeckoView:SetLocale",
            message: [
                "acceptLanguages": acceptLanguages
            ]
        )
    }
    
    public static func setDefaultPrefs(_ preferences: [String: Any]) {
        GeckoEventDispatcherWrapper.runtimeInstance.dispatch(
            type: "GeckoView:SetDefaultPrefs",
            message: preferences
        )
    }
    
    public static func dispatchEvent(type: String, message: [String: Any?]? = nil) {
        GeckoEventDispatcherWrapper.runtimeInstance.dispatch(
            type: type,
            message: message
        )
    }
    
    public static func main(
        argc: Int32,
        argv: UnsafeMutablePointer<UnsafeMutablePointer<Int8>?>
    ) {
        GeckoStartupDiagnostic.log("GeckoRuntime.main ENTER")
        MainProcessInit(argc, argv, runtime)
        GeckoStartupDiagnostic.log("GeckoRuntime.main RETURN")
    }
    
    public static func childMain(
        xpcConnection: xpc_connection_t,
        process: GeckoProcessExtension
    ) {
        GeckoStartupDiagnostic.log("helper GeckoRuntime.childMain ENTER")
        ChildProcessInit(xpcConnection, process, runtime)
        GeckoStartupDiagnostic.log("helper GeckoRuntime.childMain RETURN")
    }
}
