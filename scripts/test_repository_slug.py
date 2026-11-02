"""Fail when the hard-coded release slug drifts from the actual repository.

Release automation bakes `owner/name` into workflow gates, install scripts,
channel manifests and the CLI's self-update endpoints. A rename that updates
only some of them publishes against the old slug, so this test asserts every
copy of *this* repository's slug is the same one.

Historical documents (CHANGELOG.md and the embedded changelog snapshot) are
excluded: their links record what was true at the time, and rewriting them
would falsify release history.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent.parent
OWNER = "solos"
SLUG = f"{OWNER}/tom"

# Every file that must name the canonical `owner/repo` slug verbatim.
CHECKED = (
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    ".github/workflows/release-channels.yml",
    ".github/workflows/release-binaries.yml",
    "Cargo.toml",
    "scripts/install.sh",
    "scripts/install.ps1",
    "scripts/prebuilt-release.py",
    "scripts/refresh-channels.sh",
    "scripts/release-automation.py",
    "scripts/verify-channel-release.py",
    "scripts/winget-submit.sh",
    "crates/tom-cli/src/changelog.rs",
    "crates/tom-cli/src/prebuilt_release.rs",
    "crates/tom-cli/src/updates.rs",
)

# Release plumbing that only names the owner's tap/bucket repositories.
OWNER_ONLY = ("scripts/push-taps.sh", "scripts/release.sh")

# Directories whose GitHub slugs must all belong to this owner or an upstream
# project we intentionally reference. Documentation prose is excluded.
SCANNED = (".github", "scripts", "packaging", "crates/tom-cli/src", "deploy")
SCANNED_FILES = ("Cargo.toml", "release-plz.toml", "release-helper.rs", "Taskfile.yml")
SUFFIXES = {".yml", ".yaml", ".toml", ".sh", ".ps1", ".py", ".rs", ".json", ".rb"}
UPSTREAM_OWNERS = {
    "microsoft",        # winget-pkgs submissions
    "earendil-works",   # pi, the upstream TypeScript SDK
    "bigfish1913",      # pi-rust, this repository's direct parent project
    "fork",             # negative fixtures in scripts/test_*.py
    "contributor",
}
SLUG_PATTERN = re.compile(r"github(?:\.com|usercontent\.com)[/:](?:repos/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")


class RepositorySlugTests(unittest.TestCase):
    def test_declared_files_exist(self):
        missing = [name for name in CHECKED + OWNER_ONLY if not (ROOT / name).is_file()]
        self.assertEqual(missing, [], "test lists files that no longer exist")

    def test_release_plumbing_names_the_canonical_repository(self):
        for name in CHECKED:
            with self.subTest(file=name):
                self.assertIn(SLUG, (ROOT / name).read_text(encoding="utf-8"))
        for name in OWNER_ONLY:
            with self.subTest(file=name):
                self.assertIn(OWNER, (ROOT / name).read_text(encoding="utf-8"))

    def test_no_stale_copy_of_this_repository_slug_remains(self):
        stale = []
        for path in self.sources():
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for owner, name in SLUG_PATTERN.findall(text):
                if name != "tom" or owner in UPSTREAM_OWNERS or owner == OWNER:
                    continue
                stale.append(f"{path.relative_to(ROOT)}: {owner}/{name}")
        self.assertEqual(sorted(set(stale)), [], "release plumbing still points at another owner")

    def sources(self):
        for folder in SCANNED:
            for path in (ROOT / folder).rglob("*"):
                if path.is_file() and path.suffix in SUFFIXES:
                    yield path
        for name in SCANNED_FILES:
            yield ROOT / name


if __name__ == "__main__":
    unittest.main()
