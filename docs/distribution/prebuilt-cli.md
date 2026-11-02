# Prebuilt CLI distribution protocol v1

`tom update` resolves the latest stable version from the official GitHub Releases API and
downloads its prebuilt executable from that same repository. CLI version checks do not query
crates.io. A fresh cached answer remains available when GitHub cannot be reached; `--offline`
does not access the network. The installer requires `tom-release.json` and validates the selected
platform's distribution before downloading or replacing the executable.
Cargo compilation is an explicit alternative: `tom update --build`.

Preview builds are published only as GitHub prereleases from the `preview` branch; they are not
published to crates.io. Select that channel explicitly with `tom update preview`. Stable startup
checks never advertise prereleases, while a preview binary continues checking GitHub stable releases and
advertises the next stable release with the normal `tom update` command.

This uses the same envelope and integrity rules as the extension package
protocol. CLI Releases retain their existing `v<version>` tags. They publish
`tom-release.json`, and each target declares `binary` instead of `library`.
An executable is self-contained, so it does not require the running host's
plugin SDK ABI to match. The updater validates its exact `tom --version` output.

```json
{
  "schema_version": 1,
  "name": "tom-cli",
  "version": "0.3.24",
  "repository": "https://github.com/bigfish1913/tom",
  "tag": "v0.3.24",
  "source_commit": "0123456789abcdef0123456789abcdef01234567",
  "targets": {
    "x86_64-pc-windows-msvc": {
      "url": "https://github.com/bigfish1913/tom/releases/download/v0.3.24/tom-v0.3.24-x86_64-pc-windows-msvc.zip",
      "format": "zip",
      "size": 123456,
      "sha256": "<64 lowercase hexadecimal characters>",
      "binary": {
        "path": "tom.exe",
        "sha256": "<64 lowercase hexadecimal characters>"
      }
    }
  }
}
```

The example abbreviates the target map. Official releases contain Windows x64
MSVC, Linux x64/ARM64 GNU, and macOS Intel/Apple Silicon. No architecture or
GNU/musl substitution is allowed. Download URLs must identify the same official
repository and versioned Release. Unknown fields may be ignored; unknown schema
versions are rejected.

The updater verifies the compressed archive's byte length and SHA-256, extracts
only the declared flat `tom`/`tom.exe` file, and verifies its SHA-256 and native
object architecture. Archive traversal, links, duplicate executable entries and
oversized payloads are rejected using the extension installer's shared checks.
The downloaded executable must report exactly the requested version and must
not downgrade the running CLI.

Both download and explicit source-build paths feed the existing private staging
and atomic replacement transaction. On Windows a hidden helper waits for the
current process to exit, validates the replacement again, and rolls back on
failure. On Unix the replacement uses the same directory as the current
executable and rolls back if post-replacement validation fails.

`scripts/prebuilt-release.py` records each target's archive and executable hashes
and source commit. The release job verifies all five artifacts refer to the same
version and commit, preserves the existing archive names and `.sha256` files,
uploads archives first, and uploads `tom-release.json` last. The release driver
waits for this manifest before declaring the binaries ready.

A missing manifest means the prebuilt release is not ready. This includes older
Releases created before this protocol. The command reports the error without
falling back to source compilation or replacing the installed executable. Retry
after the assets are published, or explicitly use `tom update --build`.

`--force` permits reinstalling the resolved version; `--offline` only reports
cached update information and performs no downloads or builds.
