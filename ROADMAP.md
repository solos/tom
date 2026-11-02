# Roadmap

This is a direction document, not a commitment. It records what the project is
working on next and why, so that issues and PRs can be judged against it. For
what has already shipped, see [CHANGELOG.md](CHANGELOG.md).

Current release: **0.3.0**. Install with `cargo install tom-cli`.

## Where the project is now

`tom` is a Rust-native, library-first coding-agent runtime: ten published
crates (`tom-telemetry` → `tom-ai` → `tom-agent` → `tom-tools` →
`tom-harness` → `tom-cli`, plus `tom-tui`, `tom-plugin-sdk`,
`tom-extensions` and `tom-mcp`) and a terminal CLI built on them.

What is solid today:

- Async, streaming agent loop with tool calls, hooks, queues, cancellation and
  a faux provider for offline tests.
- Anthropic Messages and OpenAI-compatible providers, plus custom gateways via
  `models.json`.
- A Model Context Protocol client (`tom-mcp`): stdio and streamable-HTTP
  servers, tool discovery, and automatic `mcp__<server>__<tool>` injection, so
  the existing MCP tool ecosystem is usable without a plugin.
- `tool_search`: BM25 retrieval over tools that are not declared to the model,
  with the matches loaded durably, so a large MCP server no longer spends
  context on every request.
- `codemode`: the model writes JavaScript that runs in a QuickJS sandbox whose
  only capability is calling injected tools. Batch, chain, filter and branch
  flows become one call instead of many, because nested results stay in the
  script. Nested calls go through the same tool pipeline (hooks, validation,
  permission gates) as model-issued calls.
- Durable JSONL sessions with branching, compaction and crash recovery.
- A stable `#[repr(C)]` plugin ABI with a dynamic loader, lifecycle events and
  veto support.
- Remote mode: a headless `--server` and a zero-local-resource `--connect`
  client.
- Resource layout: `.tom/` project resources and `settings.json` keys.

## Near term

### 1. Distribution without a Rust toolchain

Today the only install path is `cargo install tom-cli`, which requires rustup, a
C toolchain and a full release build. Prebuilt binaries for
`x86_64`/`aarch64` on Linux, macOS and Windows, plus an install script, are the
highest-leverage change for adoption. Package-manager taps (Homebrew, Scoop,
winget) follow from the same release artifacts.

### 2. Documentation that stands on its own

- Per-crate README and `lib.rs` landing docs, so each crates.io/docs.rs page is
  usable without the workspace README.
- A task-oriented tutorial that goes from `cargo install tom-cli` to a working
  custom tool, in one page.
- Keep the parity gap list current. The honest answer to "is this really at
  parity?" is more useful than a compatibility claim.

### 3. Provider breadth

The provider boundary is in place; the gaps are adapters. Shipped today:
Anthropic Messages, OpenAI Chat Completions, OpenAI Responses, plus
OpenAI-compatible gateways including OpenRouter, DeepSeek and llama.cpp.
Also implemented: Azure OpenAI (Responses dialect) and Google Gemini, both the
Generative Language API and Vertex AI. AWS Bedrock is the remaining candidate; it
needs SigV4 signing and a credential chain (profile, IMDS, IRSA), which is a
package-sized dependency rather than a protocol adapter, so it is not planned for
the core.

### 4. Extension ecosystem

The ABI and loader work, and resource packages now let an author ship skills,
prompts, themes and extensions from npm or git without a Rust toolchain
(`tom package add`). What is still thin:

- Keep [`tom/tom-package`](https://github.com/tom/tom-package) building
  green against the current ABI and publish a compatibility table per ABI
  version.
- Ship an extension template (`cargo generate`-style) so a new extension is one
  command, not a copied example.
- Settle the Node/TypeScript bridge question: either finish it as a supported
  path or mark it explicitly experimental and stop advertising it.
- Give a resource package's `extensions/` the same version check `tom install`
  applies, so a package cannot install a cdylib built against an older ABI.

### 5. Startup initialisation (measured)

The benchmark in [`docs/performance/benchmark-vs-pi.md`](docs/performance/benchmark-vs-pi.md) puts tom
at **17.7 ms** from spawn to cold start (native Pi: 189.5 ms). Core startup is
essentially just process creation — config, session store, tool registry and the
harness are negligible (tom's `--version` and its cold start differ by 0.2 ms).

The one real startup cost is **plugin loading**, and it scales with what the user
installed: the same measurement reads ~100 ms on a machine whose
`~/.tom/agent/extensions` holds 25 plugin DLLs. So the work here is:

- make extension discovery and loading lazy (or parallel) so startup does not
  scale with the number of installed plugins;
- keep the RPC `ready` marker honest — it must keep meaning "commands are being
  accepted", not "the work was deferred somewhere later".

Reproduce with `node scripts/bench-vs-pi.mjs`. Set **both** tools' isolation
variables (`TOM_*` for tom, `PI_*` for pi) or the tom number will include your
global plugins.

Still unmeasured and worth adding: tool-loop throughput, memory growth over a
long session, compaction cost, and interactive TUI frame cost.

## Provider packages

Provider boundary cleanup keeps Anthropic and OpenAI in core. DeepSeek,
OpenRouter, llama.cpp and Proxy share one optional tom-providers package in the
independent tom-package project, with one install and upgrade entry point.
See [Provider packages](docs/architecture/provider-packages.md) for installation,
catalog registration, credential isolation and migration details.

## Later

- **Provider boundary cleanup and external adapters.** Keep the core runtime limited to the
  Anthropic Messages and OpenAI-compatible (Chat Completions/Responses) protocols.
  Move provider-specific integrations such as DeepSeek, OpenRouter, llama.cpp and
  other specialized formats out of the core provider set and let them be supplied
  by extensions or separate adapters. First introduce a provider registry/factory
  boundary, preserve `models.json` compatibility for the two core protocol families,
  and only then remove or feature-gate the extra built-in implementations. This is
  future work; the current release keeps the existing providers unchanged.
- **Multi-agent orchestration in-tree.** Sub-agents exist as an out-of-tree
  extension. The question is whether the runtime should own delegation,
  hand-off and budget accounting.
- **Editor/IDE integrations** built on the remote-mode protocol, so the agent
  is usable outside the terminal.
- **Windows parity** for anything currently POSIX-shaped in the tool layer.
- **Structured output and evaluation tooling** for teams that want to run the
  agent in CI.

## Not planned

- A hosted service. `tom` is a library and a local tool; there is no plan to
  run inference or store user sessions on project infrastructure.
- A visual/GUI application. The TUI and the JSONL remote protocol are the
  supported interfaces.
- Bundling a model. Providers are BYO-key or BYO-endpoint.

## How to influence this

Open an issue describing the problem you hit, not just the feature you want.
Features that unblock a real workflow move up; features that only add surface
area move down. If you want to work on something listed here, comment on the
issue first so we can agree on the shape before you write the patch. See
[CONTRIBUTING.md](CONTRIBUTING.md).
