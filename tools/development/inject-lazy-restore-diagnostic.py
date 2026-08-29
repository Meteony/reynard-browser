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

    print("Lazy restored-session diagnostic injected successfully.")


if __name__ == "__main__":
    main()
