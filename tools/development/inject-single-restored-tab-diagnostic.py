#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "browser/Reynard/Client/TabManagement/TabManagerImpl.swift"


def main() -> None:
    old = '''    private func createHomepageInitialTab() {
        let didRestoreTabs = restoreTabsIfNeeded()
        
        if didRestoreTabs,
'''
    new = '''    private func createHomepageInitialTab() {
        let didRestoreTabs = restoreTabsIfNeeded()

        // Diagnostic only: if restoration selected a real web tab, keep that
        // tab selected instead of immediately creating/selecting a homepage tab.
        // This gives startup tracing one restored navigation and one content path.
        if didRestoreTabs,
           let selectedTab,
           remoteURL(from: displayedURL(for: selectedTab)) != nil {
            GeckoStartupDiagnostic.log(
                "critical single-restored-tab keeping selected web tab"
            )
            return
        }
        
        if didRestoreTabs,
'''

    text = PATH.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"homepage restored-tab guard: expected exactly one anchor in {PATH}, found {count}"
        )

    PATH.write_text(text.replace(old, new, 1))
    print("Homepage startup diagnostic pinned to one restored web tab.")


if __name__ == "__main__":
    main()
