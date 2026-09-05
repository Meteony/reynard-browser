//
//  UniversalLinkManager.swift
//  Reynard
//
//  Created by Minh Ton on 12/8/26.
//

import Foundation
import GeckoView
import UIKit

final class UniversalLinkManager {
    private enum HandoffKind {
        case universalLink
        case externalScheme
    }

    private struct HandoffKey: Hashable {
        let session: ObjectIdentifier
        let uri: String
    }

    private nonisolated final class BoolGate: @unchecked Sendable {
        private let lock = NSLock()
        private var continuation: CheckedContinuation<Bool, Never>?
        private var result: Bool?

        func wait() async -> Bool {
            return await withCheckedContinuation { continuation in
                lock.lock()
                if let result {
                    lock.unlock()
                    continuation.resume(returning: result)
                    return
                }
                self.continuation = continuation
                lock.unlock()
            }
        }

        func finish(with result: Bool) {
            lock.lock()
            guard self.result == nil else {
                lock.unlock()
                return
            }
            self.result = result
            let continuation = continuation
            self.continuation = nil
            lock.unlock()
            continuation?.resume(returning: result)
        }
    }

    private static let userGestureGraceInterval: TimeInterval = 5
    private static let duplicateOpenSuppressionInterval: TimeInterval = 1

    // Schemes that belong to Gecko or represent executable/local browser content
    // must never be handed to UIApplication as external-app links.
    private static let engineHandledSchemes: Set<String> = [
        "about",
        "blob",
        "chrome",
        "data",
        "file",
        "http",
        "https",
        "jar",
        "javascript",
        "moz-extension",
        "moz-icon",
        "moz-safe-about",
        "resource",
        "view-source",
        "wyciwyg",
    ]

    private var handoffTasks: [HandoffKey: Task<Bool, Never>] = [:]
    private var confirmationTasks: [HandoffKey: Task<Bool, Never>] = [:]
    private var failedHandoffs = Set<HandoffKey>()
    private var recentSuccessfulHandoffs: [HandoffKey: Date] = [:]
    private var recentUserGestures: [ObjectIdentifier: Date] = [:]

    func decideHandoff(
        for request: LoadRequest,
        in session: GeckoSession
    ) async -> AllowOrDeny {
        guard Prefs.BrowsingSettings.openLinksInExternalApps,
              !session.isPrivateMode,
              let url = URL(string: request.uri),
              let kind = handoffKind(for: url) else {
            return .allow
        }

        // HTTP(S) Universal Links are only meaningful for top-level navigation.
        if request.isSubframe && kind != .externalScheme {
            return .allow
        }

        let sessionID = ObjectIdentifier(session)
        let now = Date()
        pruneTransientState(now: now)

        if !request.isSubframe &&
           (request.isUserInitiatedNavigation || request.hasUserGesture) {
            recentUserGestures[sessionID] = now
        }

        let isDirectlyEligible = isEligibleForExternalHandoff(
            request: request,
            sessionID: sessionID,
            now: now
        )
        let requiresConfirmation = !isDirectlyEligible &&
            kind == .externalScheme &&
            shouldOfferConfirmation(for: request)

        guard isDirectlyEligible || requiresConfirmation else {
            return .allow
        }

        if kind == .universalLink,
           let triggerUri = request.triggerUri,
           let triggerURL = URL(string: triggerUri),
           let triggerHost = triggerURL.host,
           let destinationHost = url.host,
           triggerHost.caseInsensitiveCompare(destinationHost) == .orderedSame {
            return .allow
        }

        let key = HandoffKey(session: sessionID, uri: request.uri)
        if let lastOpened = recentSuccessfulHandoffs[key],
           now.timeIntervalSince(lastOpened) < Self.duplicateOpenSuppressionInterval {
            return .deny
        }

        // Gecko's UIKit external-protocol backend cannot open custom schemes.
        // Once UIApplication has already failed for one, don't fall through to
        // Gecko and turn the same request into an engine-level load failure.
        if failedHandoffs.contains(key) {
            return kind == .externalScheme ? .deny : .allow
        }

        if requiresConfirmation {
            let confirmed = await confirmationDecision(for: key, url: url)
            guard confirmed else {
                // The request was handled by the browser UI; cancelling should
                // stop Gecko from trying the unsupported external protocol.
                return .deny
            }
        }

        if let task = handoffTasks[key] {
            return await task.value ? .deny : (kind == .externalScheme ? .deny : .allow)
        }

        let task = Task { @MainActor in
            return await open(url, kind: kind)
        }
        handoffTasks[key] = task
        defer { handoffTasks.removeValue(forKey: key) }

        let didOpen = await task.value
        if didOpen {
            failedHandoffs.remove(key)
            recentSuccessfulHandoffs[key] = Date()
        } else {
            failedHandoffs.insert(key)
        }

        if kind == .externalScheme {
            // Whether UIKit opened the app or reported that no handler exists,
            // Gecko cannot usefully continue this custom-scheme navigation.
            return .deny
        }
        return didOpen ? .deny : .allow
    }

    func didCommitNavigation(in session: GeckoSession) {
        let sessionID = ObjectIdentifier(session)
        failedHandoffs = Set(failedHandoffs.filter { $0.session != sessionID })
        pruneTransientState(now: Date())
    }

    func didCreateNewSession(from session: GeckoSession, for uri: String) {
        let key = HandoffKey(session: ObjectIdentifier(session), uri: uri)
        failedHandoffs.remove(key)
        recentSuccessfulHandoffs.removeValue(forKey: key)
    }

    private func handoffKind(for url: URL) -> HandoffKind? {
        guard let scheme = url.scheme?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
              !scheme.isEmpty else {
            return nil
        }

        if scheme == "http" || scheme == "https" {
            return URLUtils.isWebURL(url) ? .universalLink : nil
        }

        guard !Self.engineHandledSchemes.contains(scheme) else {
            return nil
        }
        return .externalScheme
    }

    private func isEligibleForExternalHandoff(
        request: LoadRequest,
        sessionID: ObjectIdentifier,
        now: Date
    ) -> Bool {
        if request.isSubframe {
            // A live user gesture may open a custom scheme directly from an
            // iframe. Gesture-less iframe attempts are handled via confirmation.
            return request.isUserInitiatedNavigation || request.hasUserGesture
        }

        if request.isUserInitiatedNavigation || request.hasUserGesture {
            return true
        }

        // Preserve user intent across a short top-level redirect chain. This is
        // important for payment/auth landing pages that navigate from HTTPS to a
        // custom app scheme after the original tap has already been consumed.
        guard let triggerUri = request.triggerUri,
              let triggerURL = URL(string: triggerUri),
              URLUtils.isWebURL(triggerURL),
              let lastGesture = recentUserGestures[sessionID] else {
            return false
        }
        return now.timeIntervalSince(lastGesture) <= Self.userGestureGraceInterval
    }

    private func shouldOfferConfirmation(for request: LoadRequest) -> Bool {
        // A subframe request necessarily originated from page content. For a
        // top-level request, require an HTTP(S) trigger so internal/browser
        // generated custom URLs cannot create unsolicited app-open prompts.
        if request.isSubframe {
            return true
        }
        guard let triggerUri = request.triggerUri,
              let triggerURL = URL(string: triggerUri) else {
            return false
        }
        return URLUtils.isWebURL(triggerURL)
    }

    private func confirmationDecision(for key: HandoffKey, url: URL) async -> Bool {
        if let task = confirmationTasks[key] {
            return await task.value
        }

        let task = Task { @MainActor in
            return await confirmExternalOpen(url)
        }
        confirmationTasks[key] = task
        defer { confirmationTasks.removeValue(forKey: key) }
        return await task.value
    }

    private func pruneTransientState(now: Date) {
        recentUserGestures = recentUserGestures.filter {
            now.timeIntervalSince($0.value) <= Self.userGestureGraceInterval
        }
        recentSuccessfulHandoffs = recentSuccessfulHandoffs.filter {
            now.timeIntervalSince($0.value) <= Self.duplicateOpenSuppressionInterval
        }
    }

    @MainActor
    private func confirmExternalOpen(_ url: URL) async -> Bool {
        guard let presenter = activePresenter(), !(presenter is UIAlertController) else {
            return false
        }

        let gate = BoolGate()
        let scheme = url.scheme?.lowercased() ?? "external"
        let alert = UIAlertController(
            title: "Open in Another App?",
            message: "This page wants to open a \(scheme) link in another app.",
            preferredStyle: .alert
        )
        alert.addAction(UIAlertAction(title: "Cancel", style: .cancel) { _ in
            gate.finish(with: false)
        })
        alert.addAction(UIAlertAction(title: "Open", style: .default) { _ in
            gate.finish(with: true)
        })

        return await withTaskCancellationHandler(operation: {
            guard !Task.isCancelled else {
                return false
            }
            presenter.present(alert, animated: true)
            return await gate.wait()
        }, onCancel: {
            gate.finish(with: false)
        })
    }

    @MainActor
    private func activePresenter() -> UIViewController? {
        var rootViewController: UIViewController?

        for case let scene as UIWindowScene in UIApplication.shared.connectedScenes
        where scene.activationState == .foregroundActive {
            if let keyWindow = scene.windows.first(where: { $0.isKeyWindow }) {
                rootViewController = keyWindow.rootViewController
                break
            }
            if rootViewController == nil {
                rootViewController = scene.windows.first?.rootViewController
            }
        }

        guard var current = rootViewController else {
            return nil
        }

        while true {
            if let presented = current.presentedViewController {
                current = presented
                continue
            }
            if let navigationController = current as? UINavigationController,
               let visible = navigationController.visibleViewController {
                current = visible
                continue
            }
            if let tabBarController = current as? UITabBarController,
               let selected = tabBarController.selectedViewController {
                current = selected
                continue
            }
            if let splitViewController = current as? UISplitViewController,
               let last = splitViewController.viewControllers.last {
                current = last
                continue
            }
            return current
        }
    }

    @MainActor
    private func open(_ url: URL, kind: HandoffKind) async -> Bool {
        let gate = BoolGate()
        let timeoutTask = Task { @MainActor in
            do {
                try await Task.sleep(nanoseconds: 5_000_000_000)
                gate.finish(with: false)
            } catch {}
        }
        defer { timeoutTask.cancel() }

        var options: [UIApplication.OpenExternalURLOptionsKey: Any] = [:]
        if kind == .universalLink {
            options[.universalLinksOnly] = true
        }

        return await withTaskCancellationHandler(operation: {
            guard !Task.isCancelled else {
                return false
            }
            UIApplication.shared.open(
                url,
                options: options,
                completionHandler: { success in
                    gate.finish(with: success)
                }
            )
            return await gate.wait()
        }, onCancel: {
            gate.finish(with: false)
        })
    }
}
