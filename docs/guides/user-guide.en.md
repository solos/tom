# tom User Guide

This guide describes the behavior implemented by the current `tom` workspace. tom is a native Rust coding-agent toolkit: the reusable runtime is published as crates, while `tom-cli` provides a ready-to-run terminal application. The examples below use the current command names, configuration paths, and extension model; they are not a generic guide for the upstream Pi project.

## 1. Install and run

### Install the CLI

Install the published binary with Rust and Cargo:

```bash
cargo install tom-cli
tom --version
tom --help
```

To build the development version from source:

```bash
git clone https://github.com/solos/tom.git
cd tom
cargo install --path crates/tom-cli --force
```

`cargo install` installs the `tom` executable. It is different from `tom install`, which installs Rust dynamic-library extensions built against `tom-plugin-sdk`.

### Build from the workspace

tom is a Cargo workspace, not a Node/npm application:

```bash
cargo run -p tom-cli
cargo run -p tom-cli -- -p "Summarize README.md"
cargo run -p tom-cli -- --mode json -p "List the crates in this project"
cargo build -p tom-cli --release
```

The release binary is `target/release/tom.exe` on Windows and normally `target/release/tom` on Linux/macOS. The offline minimal example uses the deterministic faux provider and needs neither an API key nor network access:

```bash
cargo run -p minimal
```

### First prompt

Interactive mode:

```bash
tom
tom "Explain the structure of this project"
```

One-shot mode:

```bash
tom -p "Summarize README.md"
tom --mode json -p "List the risks in this project"
```

Prefix a file with `@` to include it in the first user message:

```bash
tom @README.md "Suggest improvements for this project"
```

## 2. Models and credentials

### Credential precedence

When several sources are present, tom checks them in this order:

1. `--api-key`
2. `~/.tom/auth.json`, written by `tom auth login`
3. The provider's `apiKey` in `~/.tom/agent/models.json`
4. Environment variables

The built-in Anthropic provider accepts `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN`; built-in OpenAI uses `OPENAI_API_KEY`. DeepSeek is an optional package declaring `DEEPSEEK_API_KEY`. Provider packages declare their own `apiKeyEnv`; custom providers can explicitly reference a variable in `models.json`. Using an OpenAI-compatible protocol does not inherit `OPENAI_API_KEY`. See the [provider integration specification](../extensions/provider-integration.md). Credential checks do not make a network request:

```bash
tom auth check
tom auth check --provider gateway --json
tom auth login
tom auth logout
```

Never commit API keys to the repository, `.tom` resources, or documentation.

### Configure a custom provider

The default model catalog is `~/.tom/agent/models.json`. Set `TOM_CODING_AGENT_DIR` to relocate the whole agent configuration directory:

```jsonc
{
  "providers": {
    "gateway": {
      "api": "anthropic-messages",
      "baseUrl": "https://gateway.example.com",
      "apiKey": "sk-gateway-secret",
      "models": [{ "id": "custom-claude", "name": "Custom Claude" }]
    },
    "openai-gateway": {
      "api": "openai-completions",
      "baseUrl": "https://api.example.com/v1",
      "apiKey": "sk-openai-secret",
      "models": [{ "id": "custom-model", "name": "Custom Model" }]
    }
  }
}
```

`models` may be omitted (or left empty). tom then discovers the catalog from the provider itself at startup and for `--list-models`: OpenAI-compatible protocols read `{baseUrl}/models`, and Anthropic Messages reads `{baseUrl}/v1/models`. Results are cached in `~/.tom/agent/models.discovered.json` and merged when `models.json` is loaded, so only models whose metadata you want to pin need a manual entry. An explicit `models` list always wins; `--offline` skips the network request but still uses the last cache. Startup reuses a cached list for 15 minutes (failed attempts are cached for the same window), while `--list-models` always queries the endpoint again. In the interactive add-provider form, entering `auto` at the model-id step writes an empty list and defers to discovery.

Select a model with either a provider/model pattern or separate flags:

```bash
tom --model gateway/custom-claude -p "hello"
tom --model openai-gateway/custom-model -p "hello"
tom --provider gateway --model custom-claude -p "hello"
```

Without `--model`, tom chooses an authenticated model according to its provider catalog. A compatible Anthropic gateway can also be selected with `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN`.

## 3. CLI modes and commands

Frequently used global options:

```text
--provider <name>       provider name
--model <pattern>       model id; supports provider/model and thinking suffixes
--api-key <key>         per-run credential override
--base-url <url>        endpoint override
--timeout <seconds>     LLM request timeout, default 600
--thinking <level>      off/minimal/low/medium/high/xhigh/max
--print, -p             run once and exit
--mode text|json|rpc    output mode
--continue, -c         continue the most recent session
--resume, -r           choose a saved session
--session <id|path>    select a session
--session-dir <dir>    session directory
--tools <list>         allow only these tools
--exclude-tools <list> disable selected tools
--no-tools             disable every tool
--no-builtin-tools     disable read/bash/edit/write/docs
--no-skills            skip skill discovery
--no-prompt-templates  skip prompt-template discovery
--no-context-files     skip AGENTS.md/CLAUDE.md discovery
--no-extensions        disable extension loading
--extensions-dir <dir> scan an extra extension directory
--package-only         load only project package/resources
--offline              disable startup network checks
--export <file>        export a JSONL session as HTML
--server               start the headless JSONL server
--connect <host:port>  connect a remote TUI client
```

Subcommands include:

```text
tom auth login|check|logout
tom events path|tail
tom install <crate>
tom uninstall <crate>
tom update                 # download a verified GitHub prebuilt CLI
tom update --build         # explicitly compile with Cargo
tom dev [options]
tom dev-local [options]
tom package link|list|unlink
```

The startup `Context` summary lists the effective `SYSTEM.md`, `APPEND_SYSTEM.md`, `AGENTS.md`, and `CLAUDE.md` resources. `/context` shows the full list and `/reload` refreshes it. `/changelog` displays the release notes embedded in the current binary; `/changelog all` displays the complete history.

### Headless server and remote client

Run the agent without a local TUI and connect from another process:

```bash
tom --server --port 9899
tom --connect 127.0.0.1:9899 --token <token>

# Alternatively provide the token through the environment
export TOM_SERVER_TOKEN=<token>
tom --connect 127.0.0.1:9899
```

The server prints a token at startup and enables token authentication by default. The remote client is a display and input client: it does not load local providers, tools, sessions, or extensions. Session files and execution remain on the server. Remote mode supports runtime operations such as `/state`, `/model`, `/thinking`, `/tools`, and `/abort`; operations that require local harness state are intentionally limited. See `docs/remote/user-guide.md` for the protocol and constraints.

## 4. Built-in tools and safety boundaries

The default tool set contains Pi-compatible `read`, `bash`, `edit`, and `write`, plus tom's read-only `docs` lookup tool. Windows also registers `powershell` by default. The library includes `grep`, `find`, and `ls` implementations, but the CLI does not register them by default.

Restrict the default tool set in `.tom/settings.json`:

```json
{
  "defaultTools": ["read", "bash", "edit", "write", "docs"]
}
```

You can also choose tools per run:

```bash
tom --tools read,bash,edit,write,docs -p "Inspect and update the project"
tom --no-tools -p "Explain this error without touching files"
```

The CLI's tool selection is not a complete operating-system sandbox. Treat `bash`, `powershell`, file writes, and native extensions as trusted capabilities. Add confirmation and filesystem isolation at the product boundary when untrusted users or repositories are involved.

## 5. Project resources and precedence

Project resources live under `.tom`:

```text
project/
└── .tom/
    ├── settings.json
    ├── SYSTEM.md
    ├── APPEND_SYSTEM.md
    ├── skills/
    ├── prompts/
    ├── themes/
    └── extensions/
```

Global resources normally live under `~/.tom/agent/`. Project resources take precedence over global resources with the same name. Additional directories can be declared in `.tom/settings.json`:

```json
{
  "skillDirs": ["./team-skills"],
  "promptDirs": ["./prompts/shared"],
  "extensionDirs": ["./target/debug"]
}
```

The shorthand keys `skills`, `prompts`, and `extensions` are also supported. Paths are relative to the project root; global settings resolve relative paths against the agent directory. Use `--package-only` or `--project-only` to load only the current project's package and resources. This is different from `--local-only`, which limits extensions to explicitly supplied local paths.

Set `TOM_CODING_AGENT_DIR=/work/tom-agent` to relocate configuration and default sessions. Use `--no-session` when a temporary, non-persistent run is required.

## 6. Rust extensions

Native extensions are Rust `cdylib` libraries loaded by `tom-extensions` and linked to the stable `tom-plugin-sdk` ABI:

```bash
cargo build -p plugin-stub
tom --extensions-dir target/debug -p 'echo "hi"'
```

Install a published extension or a local development package:

```bash
tom install tom-extension-example
tom install tom-extension-example --version 0.1.0
tom install my-extension --path ../my-tom-extension --force
```

`tom install <name>` upgrades newer versions directly and skips an already installed version. Use `--force` to reinstall the same version or allow a downgrade. This also applies to Cargo builds and local installs; local changes without a version bump require `--force`.

A prebuilt archive may also carry files that the extension needs beside its library, such as a Node worker. The archive's `runtime-assets.json` index, written by the package's release builder, lists each file's path, size and SHA-256. The installer verifies every file before it installs anything, installs them beside the library in one transaction, and removes them on uninstall. Archives without an index install only the library. An `tom` build without this support also installs only the library and does not reject the archive, so upgrade `tom` before publishing a package that declares assets.

For iterative development:

```bash
cd ../my-tom-extension
tom dev
tom dev --package my-extension
tom dev-local
```

`tom dev` detects Cargo `cdylib` targets, builds the extension, loads versioned artifacts from `.tom/extensions/.dev`, and hot-reloads after source changes. If a rebuild fails, the last successfully loaded version remains active. `tom dev-local` isolates the current extension from global extensions.

Link a development package to one project:

```bash
tom package link --path ../my-extension --package my-extension
tom package list
tom package unlink my-extension
```

Project packages are stored in `.tom/packages/<name>/`. They are trusted local Rust libraries, not npm packages. Installed libraries normally live under `~/.tom/agent/extensions` or the directory selected by `TOM_CODING_AGENT_DIR`.

An extension may register tools, providers, event handlers, and resource handlers through the SDK. Keep data crossing the ABI inside SDK-defined serializable types and do not depend on private `tom-cli` modules.

## 7. SDK integration

Compose only the layers an embedded application needs:

- `tom-ai`: model types, providers, messages, and streaming events.
- `tom-agent`: the Agent loop, tools, hooks, cancellation, and events.
- `tom-tools`: built-in tools and the replaceable `ExecutionEnv` boundary.
- `tom-harness`: sessions, JSONL persistence, compaction, skills, and context files.
- `tom-cli`: the terminal application and configuration surface.

A minimal offline Agent looks like this:

```rust
use tom_agent::{Agent, AgentEvent};
use tom_ai::providers::faux::faux_provider;

let model = faux_provider().model("echo");
let mut agent = Agent::builder(model)
    .system_prompt("You are a helpful assistant.")
    .build();

let mut events = agent.subscribe();
agent.prompt("Hello from tom").await?;
while let Some(event) = events.recv().await {
    if matches!(event, AgentEvent::AgentEnd { .. }) {
        break;
    }
}
```

Implement `tom-agent::AgentTool` for a custom tool and `tom-ai::Provider` for a model adapter. Combine the faux provider with `InMemoryExecutionEnv` to test message ordering, tool calls, failures, and completion without an API key, network, or real filesystem.

## 8. Troubleshooting

### Model or endpoint errors

Run `tom auth check`, verify the provider name, model id, `models.json`, environment variables, and `baseUrl`. Use an explicit `provider/model` pattern to avoid ambiguity. Check authentication headers and endpoint compatibility before changing Agent code.

### Extension load failures

Confirm that the library is a platform-compatible `cdylib`, that its ABI version matches the host, and that `--extensions-dir` points to the directory containing the built artifact. Keep the complete host error output; it usually distinguishes discovery, loading, ABI, and registration failures.

### Event handler diagnostics

```bash
export TOM_EVENT_LOG=1
tom
tom events tail
```

The default log is `~/.tom/logs/events.jsonl`; `TOM_EVENT_LOG_PATH` overrides it. A `BeforeTuiStart` veto returns exit code `3`. Inspect whether a handler returned `Continue`, `Error`, `Abort`, `Panic`, or `Timeout`.

### Resources missing from the startup context

Place files under the project `.tom` directory or global `~/.tom/agent`. Run `tom --debug-system-prompt` to inspect the resolved system prompt, skills, and resource counts. Check project-over-global precedence and whether `--package-only`, `--no-skills`, or `--no-context-files` was supplied.

### Remote connection failures

Confirm that the server is listening on the expected address and port, and pass the exact startup token or `TOM_SERVER_TOKEN`. Remember that the client loads no local agent resources; provider credentials, extensions, and sessions must be available on the server.

## 9. Development, tests, and releases

Run the workspace checks before changing public APIs:

```bash
cargo fmt --all
cargo check --workspace
cargo test --workspace
```

The normal dependency publication order is:

```text
tom-telemetry -> tom-ai -> tom-agent -> tom-tools -> tom-harness
tom-plugin-sdk -> tom-extensions -> tom-tui -> tom-cli
```

When a release changes user-visible behavior, update the release notes, README, website `data/docs.json`, and both language versions of this guide. The website is a static site; updating the Markdown source does not publish it automatically—run the repository's deployment task after building.

## 10. Documentation map

- Online documentation: https://tom.laofu.online/docs.html
- Repository: https://github.com/solos/tom
- Rust API: https://docs.rs/tom-agent and https://docs.rs/tom-plugin-sdk
- Extension authoring: https://tom.laofu.online/extension-authoring.md
- Remote mode: `docs/remote/user-guide.md`
- Architecture: `docs/architecture/overview.md`

When the online site and an installed binary differ, use the documentation shipped with the matching Git tag and release. The CLI's `docs` tool can query the local documentation snapshot without depending on the website.

### CLI self-update distribution

`tom update` resolves the released version through crates.io and downloads the matching GitHub `tom-release.json` distribution. It verifies the exact target, archive size, archive and executable SHA-256, and the executable’s version before transactional replacement. Windows applies the staged update after the running process exits. Missing manifests and failed downloads/checks do not silently invoke Cargo; use `--build` explicitly. `--force` reinstalls the resolved version and `--offline` only reports cached information. See [the CLI distribution protocol](../distribution/prebuilt-cli.md).
