#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "browser/Reynard/Client/TabManagement/TabManagerImpl.swift"


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
        """        regularTabs = snapshot.regularTabs.map { snapshot in
            let tab = Tab(
                id: snapshot.id,
                session: createSession(
                    tabID: snapshot.id,
                    url: snapshot.url,
                    windowId: nil,
                    isPrivate: false
                ),
""",
        """        regularTabs = snapshot.regularTabs.map { snapshot in
            let tab = Tab(
                id: snapshot.id,
                session: createSession(
                    tabID: snapshot.id,
                    url: snapshot.url,
                    windowId: nil,
                    isPrivate: false,
                    opening: .manual
                ),
""",
        "regular restored tabs",
    )

    replace_once(
        """        privateTabs = snapshot.privateTabs.map { snapshot in
            let tab = Tab(
                id: snapshot.id,
                session: createSession(
                    tabID: snapshot.id,
                    url: snapshot.url,
                    windowId: nil,
                    isPrivate: true
                ),
""",
        """        privateTabs = snapshot.privateTabs.map { snapshot in
            let tab = Tab(
                id: snapshot.id,
                session: createSession(
                    tabID: snapshot.id,
                    url: snapshot.url,
                    windowId: nil,
                    isPrivate: true,
                    opening: .manual
                ),
""",
        "private restored tabs",
    )

    replace_once(
        """        if tabs(for: selectedTabMode).isEmpty {
            selectedTabMode = regularTabs.isEmpty ? .private : .regular
        }
        
        delegate?.tabManagerDidChangeTabs(self)
""",
        """        if tabs(for: selectedTabMode).isEmpty {
            selectedTabMode = regularTabs.isEmpty ? .private : .regular
        }

        // Keep the user's saved selection when it is a real web page. For this
        // diagnostic only, fall back to another restored HTTP(S) tab when the
        // saved selection is blank so first-paint timing is meaningful.
        let diagnosticSelectedTabs = tabs(for: selectedTabMode)
        let diagnosticSelectedIndex = selectedIndex(for: selectedTabMode)
        let diagnosticSelectionHasRemoteURL =
            diagnosticSelectedTabs.indices.contains(diagnosticSelectedIndex) &&
            remoteURL(from: displayedURL(for: diagnosticSelectedTabs[diagnosticSelectedIndex])) != nil

        if !diagnosticSelectionHasRemoteURL {
            if let index = regularTabs.lastIndex(where: {
                remoteURL(from: displayedURL(for: $0)) != nil
            }) {
                selectedTabMode = .regular
                selectedRegularTabIndex = index
            } else if let index = privateTabs.lastIndex(where: {
                remoteURL(from: displayedURL(for: $0)) != nil
            }) {
                selectedTabMode = .private
                selectedPrivateTabIndex = index
            }
        }
        
        delegate?.tabManagerDidChangeTabs(self)
""",
        "diagnostic restored web-tab fallback",
    )

    replace_once(
        """    private func createSession(
        tabID: UUID,
        url: String?,
        windowId: String?,
        isPrivate: Bool
    ) -> GeckoSession {
        return sessionManager.createSession(
            url: url,
            tabID: tabID,
            isPrivate: isPrivate,
            opening: .immediate(windowID: windowId),
            delegates: sessionDelegates
        )
    }
""",
        """    private func createSession(
        tabID: UUID,
        url: String?,
        windowId: String?,
        isPrivate: Bool,
        opening: SessionOpening? = nil
    ) -> GeckoSession {
        return sessionManager.createSession(
            url: url,
            tabID: tabID,
            isPrivate: isPrivate,
            opening: opening ?? .immediate(windowID: windowId),
            delegates: sessionDelegates
        )
    }
""",
        "session factory",
    )

    print("Lazy restored-session diagnostic injected with web-tab timing fallback.")


if __name__ == "__main__":
    main()
