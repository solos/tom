# tom 使用手册

这是一份面向使用者和扩展作者的 tom 手册，涵盖安装、配置、会话、插件、远程模式和故障排查。
具体实现以当前仓库和已安装的 tom 二进制为准。

## 1. 安装

### 直接安装 CLI

需要 Rust/Cargo：

```bash
cargo install tom-cli
tom --version
tom --help
```

从本仓库源码安装开发版本：

```bash
git clone https://github.com/solos/tom.git
cd tom
cargo install --path crates/tom-cli --force
```

`cargo install` 安装的是可执行文件；它不等同于 `tom install`。后者用于安装由 `tom-plugin-sdk` 构建的 Rust 动态库扩展。

### 从源码启动与构建

本项目是 Rust Cargo workspace，不是 Node/npm 项目，根目录没有 `package.json`。在仓库根目录执行：

```bash
# 直接启动 CLI
cargo run -p tom-cli

# 向 CLI 传递参数（`--` 后的内容属于 tom）
cargo run -p tom-cli -- -p "总结 README.md"
cargo run -p tom-cli -- --mode json -p "列出项目中的 crates"

# 构建 release 版本
cargo build -p tom-cli --release
```

构建完成后，Windows 可执行文件位于 `target/release/tom.exe`，Linux/macOS 下通常为 `target/release/tom`。也可以把本地 CLI 安装到 Cargo 的 bin 目录后直接使用：

```bash
cargo install --path crates/tom-cli --force
tom
```

离线示例（不需要 API Key 或网络）可以使用：

```bash
cargo run -p minimal
```

### 第一次运行

交互模式：

```bash
tom
tom "解释当前项目的目录结构"
```

单次输出模式：

```bash
tom -p "总结 README.md"
tom --mode json -p "列出项目的风险"
```

通过 `@` 把文件放进第一条消息：

```bash
tom @README.md "给出这个项目的改进建议"
```

## 2. 模型和凭据

### 凭据优先级

当多个来源同时存在时，优先级为：

1. `--api-key`
2. `~/.tom/auth.json`（由 `tom auth login` 写入）
3. `~/.tom/agent/models.json` 中对应 provider 的 `apiKey`
4. 环境变量

Anthropic 使用 `ANTHROPIC_API_KEY` 或 `ANTHROPIC_AUTH_TOKEN`；OpenAI-compatible provider 使用 `OPENAI_API_KEY`。检查凭据时不会发起网络请求：

```bash
tom auth check
tom auth check --provider gateway --json
tom auth login
tom auth logout
```

不要把密钥写入 Git 仓库或项目文档。

### 自定义 Provider

配置文件默认是 `~/.tom/agent/models.json`，也可以通过 `TOM_CODING_AGENT_DIR` 指定 agent 配置目录：

```jsonc
{
  "providers": {
    "gateway": {
      "api": "anthropic-messages",
      "baseUrl": "https://gateway.example.com",
      "apiKey": "sk-gateway-secret",
      "models": [
        { "id": "custom-claude", "name": "Custom Claude" }
      ]
    },
    "openai-gateway": {
      "api": "openai-completions",
      "baseUrl": "https://api.example.com/v1",
      "apiKey": "sk-openai-secret",
      "models": [
        { "id": "custom-model", "name": "Custom Model" }
      ]
    }
  }
}
```

`models` 可以省略（或留空）。此时 tom 会在启动时以及 `--list-models` 时自动向 provider 拉取模型目录：OpenAI 兼容协议读取 `{baseUrl}/models`，Anthropic Messages 读取 `{baseUrl}/v1/models`。结果缓存在 `~/.tom/agent/models.discovered.json`，加载 `models.json` 时合并到对应 provider；只有需要固定元数据（上下文窗口、价格、thinking 级别等）的模型才需要手写。显式配置的 `models` 始终优先；`--offline` 跳过网络请求，但仍使用上次的缓存。启动时缓存有效期为 15 分钟（拉取失败也会缓存同样时长，避免每次启动都等待超时），而 `--list-models` 总是重新向端点查询。交互式添加 provider 时，在 model id 一步输入 `auto` 也会写入空列表并交给自动发现。

模型条目还可以配置 `cost`，单价单位为 **美元 / 百万 token**，例如：

```json
{
  "id": "custom-model",
  "cost": {
    "input": 2,
    "output": 8,
    "cacheRead": 0.2,
    "cacheWrite": 2.5
  }
}
```

以上为示例价格。宿主按每次实际用量计算 `usage.cost`，供页脚和统计插件累计展示费用。
可选的 `cost.tiers` 数组用于阶梯定价，每项包含相同的四个价格字段和 `inputTokensAbove`；
当输入与缓存 token 总数超过阈值时，使用已超过的最高阈值对应的价格。
未配置 `cost` 的自定义模型默认使用零单价。修改配置后重启 tom 生效。

选择模型：

```bash
tom --model gateway/custom-claude -p "hello"
tom --model openai-gateway/custom-model -p "hello"
tom --provider gateway --model custom-claude -p "hello"
```

不传 `--model` 时，tom 会优先选择已经认证的模型。标准 Anthropic 凭据存在时使用内置默认模型；只有自定义 gateway 已认证时，会选择该 gateway 的第一个可用模型。

Anthropic 的兼容网关还可以使用：

```text
ANTHROPIC_BASE_URL=https://gateway.example.com
ANTHROPIC_AUTH_TOKEN=token
```

### 内置协议一览

`models.json` 的 `api` 字段决定 wire 协议。核心内建这些：

| `api` | 认证 | 端点 |
| --- | --- | --- |
| `anthropic-messages` | `x-api-key` / bearer | `ANTHROPIC_BASE_URL` 或 `baseUrl` |
| `openai-completions` | bearer | `OPENAI_API_KEY` 或 `baseUrl` |
| `openai-responses` | bearer | `baseUrl` |
| `azure-openai-responses` | bearer | `AZURE_OPENAI_BASE_URL` / 资源名 |
| `google-generative-ai` | `x-goog-api-key` | `GOOGLE_API_KEY` / `GEMINI_API_KEY` |
| `google-vertex` | bearer | `GOOGLE_VERTEX_ACCESS_TOKEN`，区域主机由 location 推出 |

Azure 示例（部署名和 api-version 都可省略）：

```jsonc
{
  "providers": {
    "azure": {
      "api": "azure-openai-responses",
      "baseUrl": "https://my-resource.openai.azure.com",
      "apiKey": "sk-azure",
      "models": [{ "id": "gpt-4o-mini" }]
    }
  }
}
```

部署名与模型 id 不一致时用 `AZURE_OPENAI_DEPLOYMENT_NAME_MAP="gpt-4o-mini=prod-mini"`
映射；`api-version` 默认 `v1`，可用 `AZURE_OPENAI_API_VERSION` 覆盖。

Gemini / Vertex：

```jsonc
{
  "providers": {
    "gemini": {
      "api": "google-generative-ai",
      "apiKey": "GOOGLE_API_KEY",
      "models": [{ "id": "gemini-2.5-pro" }]
    }
  }
}
```

Vertex 需要 project 与 location（`GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION`），
认证用导出的 access token（`GOOGLE_VERTEX_ACCESS_TOKEN`）或 API key；自动获取 ADC
不在核心内实现。

AWS Bedrock 不在核心实现：它需要 SigV4 签名与完整凭证链，依赖成本高于协议适配，
请通过扩展提供。

### 资源包（npm / git，无需 Rust 工具链）

`tom install` 装的是**编译好的 Rust 扩展**，作者必须有工具链。资源包是另一条路：
把 skills / prompts / themes / extensions 打成一个包，从 npm 或 git 安装。

```bash
tom package add npm:my-tom-pack            # 用户级 ~/.tom/agent/packages
tom package add npm:@acme/pack@1.2.0 -l    # 项目级 ./.tom/packages
tom package add git:github.com/me/pack#v1
tom package add ./my-pack --force
tom package list-resources
tom package remove my-tom-pack
```

包可以用 `tom-package.json` 描述，或者在 `package.json` 里写 `tom`（也接受 `pi`，
所以现成的 pi 包可以直接装）：

```json
{
  "name": "my-tom-pack",
  "version": "1.0.0",
  "tom": {
    "skills": ["./resources/skills"],
    "prompts": ["prompts/*.md"],
    "themes": ["./resources/themes"]
  }
}
```

完全不写清单也可以：`extensions/`、`skills/`、`prompts/`、`themes/` 会被自动发现。

安全边界：

- npm 包会校验 registry 的 `dist.integrity`（sha512/sha256）或 `shasum`，校验失败不解包。
- 安装先落到临时目录再改名，失败不会留下半个包。
- 每个安装目录里有 `.tom-managed.json` 标记；`tom package remove` 只删带标记的目录，
  覆盖手写目录必须显式 `--force`。
- 手工维护的目录用 `tom package adopt <dir>` 接管后就能被 `remove` 管理。

包资源与手写资源的优先级：项目包 > 项目 `.tom/<kind>` > 用户包 > 用户 `<agent>/<kind>`，
同名按 first-registration-wins（与既有语义一致）。

## 3. CLI 命令

常用全局选项：

```text
--provider <name>       Provider 名称
--model <pattern>       模型 ID，支持 provider/model 和 thinking 后缀
--api-key <key>         本次运行覆盖凭据
--base-url <url>        覆盖模型 endpoint
--timeout <seconds>     LLM API 请求超时（默认 600）
--thinking <level>      off/minimal/low/medium/high/xhigh/max
--print, -p             单次运行并退出
--mode text|json|rpc    输出模式
--continue, -c          继续最近会话
--resume, -r            选择历史会话
--session <id|path>     指定会话
--session-dir <dir>     指定会话目录
--name, -n <name>       设置会话显示名称
--tools <list>          只允许指定工具
--exclude-tools <list>  禁用指定工具
--no-tools              禁用所有工具
--no-builtin-tools      禁用内置工具（read/bash/edit/write/docs）
--no-skills             跳过技能发现
--no-prompt-templates   跳过 prompt-template 发现
--no-context-files      跳过 AGENTS.md/CLAUDE.md 发现
--no-extensions         禁用扩展加载
--extensions-dir <dir>  额外扫描 Rust 扩展目录
--package-only         只加载当前项目 package/resource，排除全局资源
--project-only         `--package-only` 的等价别名
--list-models [search]  列出可用模型（可带模糊搜索）
--offline               禁用启动时的网络检查
--export <file>         把 JSONL 会话导出为 HTML
--tui-mode <mode>       TUI buffer：regular 或 fullscreen
--system-prompt <text>  替换默认系统提示词
--append-system-prompt <text>  追加系统提示词（可重复）
--debug-system-prompt   把解析后的系统提示词各段打印到 stderr
--verbose               显示启动警告（如被忽略的 flag）
--server [--port <n>] [--bind <ip>]
                        无头服务端（启动时打印 token）
--connect <host:port>   远程客户端 TUI（零本地资源）
--token <token>         远程认证 token（也支持环境变量 TOM_SERVER_TOKEN）
```

子命令：

```text
tom auth login|check|logout
tom events path|tail    检查扩展事件日志（需 TOM_EVENT_LOG=1）
tom install <crate>
tom uninstall <crate>
tom update                 # 更新 tom CLI 自身
tom dev [options]          # 开发 Rust 扩展：编译、watch、热重载
tom dev-local [options]    # 只调试当前 Rust 扩展（隔离模式）
tom package link|list|unlink # 管理项目本地 Rust 扩展包
```

### CLI 自更新

`tom update` 默认从 GitHub Release 下载预编译的 CLI，不需要本地 Rust/Cargo。
版本按 crates.io 的发布记录解析；`tom-release.json` 提供各平台下载地址、大小和
压缩包/可执行文件的 SHA-256。校验目标平台、完整性和实际版本后，原子替换当前 CLI。
Windows 会暂存更新，等待当前进程退出后完成替换。

`tom update --force` 重新安装已解析的版本；`tom update --build` 显式使用 Cargo 源码编译。
缺少 manifest、下载失败或校验不通过都会报错并保留原版本，不会自动转为编译。
`--offline` 仅报告缓存的版本信息，不下载也不编译。旧 Release 没有 manifest 时，
可等待协议资产补齐，或显式使用 `tom update --build`。

### 启动资源清单

启动 TUI 时，`Context` 会列出实际加载成功的系统提示词和项目指令文件路径，
包括 `SYSTEM.md`、`APPEND_SYSTEM.md` 以及 `AGENTS.md` / `CLAUDE.md`。
项目 `SYSTEM.md` 和 `APPEND_SYSTEM.md` 优先于全局同名文件；清单只显示生效的来源。
没有加载文件时，启动页会省略 `Context`。`/context` 可查看当前完整资源清单，
成功执行 `/reload` 后，启动页的 `Context` 和 `/context` 都会更新。
设置 `quietStartup: true` 可隐藏启动资源清单。

### 更新日志

`/changelog` 显示当前二进制对应的最新发布说明；`/changelog all` 显示完整历史。
更新后第一次启动新交互会话，会展示自上次阅读以来的新版本说明，后续启动不再重复。
恢复已有会话时，提示会延后到下一次新会话。

tom 使用全局 `settings.json` 中的 `lastTomChangelogVersion` 记录已读版本，避免导入的
`lastChangelogVersion` 干扰。已有配置缺少 tom 标记时，只补充展示当前版本一次；首次安装
直接建立基线。设置 `collapseChangelog: true` 可显示简短更新提示。

### 终端、编辑器与分支摘要

以下四项在 `settings.json` 中配置：

| 键 | 作用 |
| --- | --- |
| `shellPath` | `bash` 工具与 RPC `bash` 命令使用的解释器。默认按平台选择；指定 PowerShell 路径时会自动改用其非交互参数 |
| `shellCommandPrefix` | 追加在每条 shell 命令前的语句（例如 `shopt -s expand_aliases`） |
| `externalEditor` | 外部编辑器命令，优先于 `$VISUAL` / `$EDITOR` |
| `treeFilterMode` | `/tree` 打开时的过滤：`default`（隐藏工具结果）、`no-tools`、`user-only`、`labeled-only`、`all` |

分支摘要由 `branchSummary` 控制：`reserveTokens` 限定摘要请求的 token 预算，
`skipPrompt: true` 表示切分支时不生成摘要。

```json
{
  "shellPath": "/bin/zsh",
  "externalEditor": "code --wait",
  "treeFilterMode": "user-only",
  "branchSummary": { "reserveTokens": 16384, "skipPrompt": false }
}
```

### 跳到最新消息

在 `--tui-mode fullscreen` 和 `--connect` 中，向上滚动回看历史时，消息区底部会显示
`↓ Jump to latest message · End`。点击提示或按 `End` 即可回到最新消息，并恢复跟随输出；
输入框中的草稿和焦点会保留。

可在 `settings.json` 的 `keybindings` 中设置 `"tui.altScreen.bottom": "ctrl+end"`。
提示会显示实际快捷键；设置为 `null` 可禁用按键，点击入口仍可使用。

### 远程模式（`--server` / `--connect`）

把 agent 跑在无头服务端，另一个进程用 TUI 远程驱动。客户端**无任何本地 agent 资源**。

```bash
tom --server --port 9899          # 服务端：启动时打印 token
tom --connect 127.0.0.1:9899 --token <token>   # 客户端

# 或通过环境变量传递 token
export TOM_SERVER_TOKEN=<token>
tom --connect 127.0.0.1:9899
```

服务端默认开启 token 认证（`--no-token` 可关闭）。客户端支持 `/state`、`/model`、
`/thinking`、`/tools`、`/abort` 等命令；`/tree`、`/fork`、`/switch`、`/export`、
`/name`、`/reload` 依赖本地 harness，在远程模式下不可用。完整协议、可用命令与
限制见 [`remote-mode.md`](../remote/user-guide.md)。

## 4. 内置工具

默认工具包含 Pi 的 `read`、`bash`、`edit`、`write`，以及 tom 自带的只读 `docs` 文档查询工具。Windows 上还会默认注册 `powershell`。`docs` 可以查询使用手册、扩展开发、Agent 项目结构、Rust 调试和架构说明；`grep`、`find`、`ls` 仍保留为库实现，但不由 CLI 默认注册。

可以通过 `.tom/settings.json` 的 `defaultTools` 字段（或简写 `default_tools`）在未指定
`--tools` 时限定启动工具集：

```json
{
  "defaultTools": ["read", "bash", "edit", "write", "docs"]
}
```

需要限制工具范围时，显式列出 Pi 的四个工具：

```bash
tom --tools read,bash,edit,write,docs -p "检查并修改项目文件"
```

### 工具膨胀与 `tool_search`

MCP 服务器接上之后，声明给模型的工具会迅速变多（一个 filesystem 服务器就有
10+ 个）。`tool_search` 让模型用一句话找工具，而不是每次请求都声明全部：

- 检索方式：BM25，搜索工具名、描述与参数 schema 的属性名/说明。
- 命中的工具会进入 active 集合，并写成一条 `active_tools_change` 条目，因此
  `/tree`、续接会话与 fork 之后仍然声明；同一次运行的下一轮请求即可调用。
- 在 `mcp.json` 里用 `"exposure": "deferred"` 把某个服务器的工具移出声明集合：

```json
{ "mcpServers": { "filesystem": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "."], "exposure": "deferred" } } }
```

默认是 `direct`。延迟声明是权衡：每次加载要多花一次检索调用，所以只对大工具集
划算。详见 [MCP 服务器](../mcp/README.md)。

## 5. 项目目录和资源优先级

tom 使用自己的 `.tom` 目录：

```text
项目/
└── .tom/
    ├── settings.json
    ├── SYSTEM.md
    ├── APPEND_SYSTEM.md
    ├── skills/
    ├── prompts/
    ├── themes/
    └── extensions/
```

全局资源默认位于 `~/.tom/agent/`，包括 `settings.json`、`models.json`、`skills/`、`prompts/`、`themes/` 和 `extensions/`。同名资源发生冲突时，项目资源优先于全局资源。

### 自定义主题

主题文件是 pi 兼容的 JSON（`name` + `colors`，支持 `#rrggbb`、`oklch()`/`okhsl()`、
0-255 调色板索引与 `vars` 变量引用；缺省字段回落默认配色）。三个来源可用：

- 内置 preset：`dark` / `light` / `monochrome`；
- 文件路径：`tom --theme ~/ocean.json`，或 `settings.json` 的 `"theme"` 字段写路径
  （`--theme` 优先于 settings；加载失败时警告并回落默认主题，不阻断启动）；
- 主题目录发现：`~/.tom/agent/themes/*.json`（全局）与 `.tom/themes/*.json`（项目，
  优先于全局）。`/theme` 选择器在三个内置项之后列出发现的主题（按文件名），
  选中即生效并持久化；`/theme <名字>` 直达应用。扩展包也可贡献主题
  （`resources_discover` 的 `themePaths`，优先级在目录之后）。

`--no-themes` 关闭目录发现与扩展主题（内置 preset 仍可用）。untrusted 项目不会
加载其 `.tom/themes/`；`/reload` 会重建主题列表，被移除的激活主题回落默认配色。

项目级 `.tom/settings.json` 可以追加资源目录：

```json
{
  "skillDirs": ["./team-skills"],
  "promptDirs": ["./prompts/shared"],
  "extensionDirs": ["./target/debug"]
}
```

路径相对于项目根目录；`skills`、`prompts`、`extensions` 是对应 `*Dirs` 字段的简写。自定义目录会与 `.tom` 和全局约定目录一起加载。全局 `~/.tom/agent/settings.json` 也支持这些字段，相对路径相对于 agent 目录。

只加载当前项目的 package/resource、排除全局资源时，使用以下任一等价参数：

```bash
tom --package-only
tom --project-only
```

两者都会加载当前项目的 skills、prompts、themes、extensions 和 packages，并读取项目 `.tom/settings.json`；不会自动加载全局资源。`--local-only` 语义不同，只加载通过 `--extensions-dir` 或 `--extension` 显式指定的扩展。

配置目录可以重定位：

```bash
TOM_CODING_AGENT_DIR=/work/tom-agent tom
```

会话默认保存到 agent 配置目录下的 sessions；`--no-session` 可使用临时会话。

## 6. Rust 插件

Rust 原生插件是 `cdylib`，只依赖 `tom-plugin-sdk`，由 `tom-extensions` 动态加载：

```bash
cargo build -p plugin-stub
tom --extensions-dir target/debug -p 'echo "hi"'
```

安装预编译扩展（默认，不需要 Rust/Cargo）：

```bash
tom install tom-todo
tom install tom-todo --version 0.2.0
tom install tom-todo --force # 同版本重装
```

`tom install <包名>` 可直接安装或升级；目标版本已安装时会提示并跳过。同版本重装或降级需要 `--force`。源码构建也遵循这一规则，本地开发修改代码但未更改版本时，使用 `--force` 重装。

安装器从 crates.io 选择最新未撤回的稳定版本，并用包的 `repository` 元数据找到 GitHub 仓库，再读取 `<包名>-v<版本>` Release 中的 `tom-extension.json`。它按精确目标三元组匹配预编译文件，校验压缩包大小和 SHA-256、解压后的库文件 SHA-256、平台架构及声明的 SDK ABI。库文件名以 manifest 的 `library.path` 为准。同一仓库里的扩展可以独立版本发布。

指定自定义 GitHub 仓库（也接受完整 HTTPS 仓库 URL）：

```bash
tom install my-extension --github owner/repo --version 1.2.3
tom install my-extension --github https://github.com/owner/repo
```

自定义仓库也须发布同一分发协议。显式仓库不依赖 crates.io；省略版本时，只在该仓库的 `<包名>-v<版本>` 标签中选择最新稳定版本。不会使用仓库的全局 latest Release。后续 `--force` 重装和启动更新检查会保留来源，并核对新版本的 manifest 是否适配当前平台。

发布者必须先上传所声明平台的压缩包，最后上传 manifest。manifest 尚未发布、目标平台缺失或校验不通过时安装失败，不会自动编译或选择其他版本。需要源码编译时显式使用：

```bash
tom install tom-todo --build
tom install tom-todo --build --version 0.2.0 --force
```

预编译安装记录包括版本、仓库、目标平台、源码提交、SDK ABI 和校验值；安装与卸载使用同一事务机制。加载时仍会验证实际插件入口与 API 结构大小。系统原生运行库依赖仍由操作系统提供。

包可以在库文件旁附带运行所需的文件，例如 Node 工作进程 `runtime/main.mjs`。压缩包根目录的 `runtime-assets.json` 索引由包的发布构建工具生成，列出每个文件的路径、大小和 SHA-256。安装器先在内存中校验全部内容，再与库文件一起以事务方式写入扩展目录，并记录在安装注册表中。升级会替换这些文件；卸载会连同因此变空的目录一并删除。路径须为相对的 ASCII 普通路径，不得包含 `..`、隐藏组件、`node_modules`、原生库后缀、Windows 设备名（如 `CON`、`NUL`、`COM1`）、以点结尾的组件、符号链接或索引未声明的文件；单文件不超过 128 MiB，展开后的总量不超过 256 MiB，压缩包条目总数不超过 128。没有索引的压缩包只安装库文件。旧版 tom 不支持此功能：它读取这类压缩包时只安装库文件而不会拒绝，因此发布声明了附属文件的包之前，应先升级 tom。

本地开发：

```bash
tom install my-extension --path ../my-tom-extension --force
```

开发扩展项目时使用 watch 模式：

```bash
cd ../my-tom-extension
tom dev
# 多扩展 workspace：tom dev --package my-extension
# 只调试当前扩展：tom dev-local（隔离模式，不加载全局扩展）
```

`tom dev` 会自动识别 Cargo `cdylib`、首次编译并从 `.tom/extensions/.dev` 加载版本化产物。源码变化会触发重新编译和热重载；手工执行 `/reload` 也会先重新编译。编译失败时继续保留当前已经加载的版本。

如果希望把开发好的扩展固定到某个项目，可使用项目包命令：

```bash
tom package link --path ../my-extension --package my-extension
tom package list
# 之后在该项目目录直接运行 tom 即可加载
tom package unlink my-extension
```

项目包位于 `.tom/packages/<name>/`，是受信任的本机 Rust 动态库；它不是 npm/Node Pi package。全局安装仍使用 `tom install`。完整模板和边界规则见在线扩展作者指南：<https://tom.laofu.online/extension-authoring.md>`，调试技巧见 `docs` 的 `debugging` 主题。

安装后的动态库位于 `~/.tom/agent/extensions`（或 `TOM_CODING_AGENT_DIR` 指定的目录），下次启动 tom 时加载。插件通过稳定 ABI 注册工具、Provider、事件处理器和资源处理器；不要直接依赖 `tom-cli` 的私有模块。

### 网页搜索与抓取

联网工具由独立的 [tom-package 扩展](https://github.com/tom/tom-package) 提供，
不属于 CLI 默认内置工具。按需安装后重启 tom：

```bash
tom install tom-websearch
tom install tom-webfetch
```

- `websearch` 返回搜索结果的标题、链接和摘要。
- `webfetch` 提取公开 HTTP(S) 网页的可读文本；会拒绝私有地址和超限响应。
- 这两个扩展不是交互式浏览器，不提供点击、登录流程或网页 JavaScript 执行。

### 继承主会话配置的子 agent

安装兼容版本的 `tom-subagents` 并重启后，可通过 `delegate_task` 委派任务：

```bash
tom install tom-subagents
```

子 agent 使用主会话当前有效配置的快照：模型/provider 及其私有凭据绑定、thinking、
系统提示词、资源、请求选项、启用的工具、项目 cwd 和审批 hook。它不是重新读取默认
配置启动的 `tom` 子进程；凭据不会通过插件 JSON 传递。

子任务使用独立的内存 Session，**不复制或修改父聊天历史**。宿主 API 可进一步缩小
工具集合，但不能扩大；子工具集中移除 `delegate_task`，并禁止通过别名递归委派。
审批与 `ask_user` 沿用父 UI；没有交互消费者时保留明确拒绝/报错，不会默认放行。
父运行结束或取消、会话切换以及所属插件卸载/reload 会取消子任务。
这不是 OS 安全沙箱，允许的 shell 等工具仍保有正常能力。

宿主与扩展需同时支持对应协议；旧宿主明确要求升级，不回退到默认配置的子进程。
SDK 提供 `AgentHarness::create_child`，扩展通过 `GetExecutionContext` 和 `ChildAgent`
runtime actions 接入。完整边界与生命周期见 [子 agent 协议](../extensions/subagents.md)。

## 7. SDK 集成

只需要嵌入 Agent 时，依赖 `tom-agent` 和 `tom-ai`；需要内置工具时再加入 `tom-tools`；需要会话、压缩、skills 和上下文文件时加入 `tom-harness`。

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

自定义工具实现 `tom-agent::AgentTool`；Provider 实现 `tom-ai::Provider`。使用 `faux provider` 和 `InMemoryExecutionEnv` 可以在没有网络、API key 或真实文件系统的情况下测试 Agent loop。

## 8. 故障排查

### 找不到模型或接口报错

运行 `tom auth check`，确认 provider、`models.json`、环境变量和 `baseUrl`。使用 `--provider` 和完整的 `provider/model` 避免同名模型歧义。接口错误会保留 provider 返回的诊断文本；先检查 endpoint、认证头和模型 ID。

### 扩展加载失败

确认 Rust 插件是 `cdylib` 并与当前平台匹配；临时使用 `--extensions-dir` 指向生成目录。加载失败时保留宿主输出的完整错误信息，检查扩展是否声明了宿主未提供的能力。

### 扩展事件处理器没触发或启动被中止

```bash
export TOM_EVENT_LOG=1
tom            # 记录所有扩展事件处理器调用
tom events tail   # 跟踪日志；看 result 是 Continue 还是 Error/Abort/Panic/Timeout
```

日志默认在 `~/.tom/logs/events.jsonl`（可用 `TOM_EVENT_LOG_PATH` 覆盖）。如果
`BeforeTuiStart` 阶段有扩展返回 veto（`EVENT_HANDLER_ABORT`），CLI 以退出码 `3`
中止启动并打印原因。

### 资源没有出现在欢迎页

确认文件位于 `.tom`（或兼容的 `.pi`）或全局 `~/.tom/agent`。使用 `tom --debug-system-prompt` 查看最终系统提示词、skills 和资源计数；同名资源优先检查 `.tom` 是否覆盖了 `.pi`。

### 远程模式连不上

确认服务端已用 `tom --server --port <port>` 启动且 token 正确（或通过
`TOM_SERVER_TOKEN` 提供）。客户端是纯显示端，不加载任何本地 provider/工具/扩展；
会话文件在服务端。

## 9. 开发、测试和发布

运行格式化、检查和测试：

```bash
cargo fmt --all
cargo check --workspace
cargo test --workspace
```

发布 crate 时按依赖顺序：

```text
tom-telemetry → tom-ai → tom-agent → tom-tools → tom-harness →
tom-plugin-sdk → tom-extensions → tom-tui → tom-cli
```

日常贡献无需手动修改版本号。普通改动合并 `main` 并通过 CI 后，由自动化准备
Release PR；只有合并符合条件的 Release PR 才会发布。发布记录统一维护在根目录
`CHANGELOG.md`，不再新建 `docs/release-vX.Y.Z.md`。完整流程与纯文档不发布的处理方式
见 [发布流程](../maintaining/releasing.md)。

修改模型可读文档源 `docs/tom-tool/` 后运行 `sh scripts/sync-embedded-docs.sh` 并提交
生成的文档快照。仅更新文档不需要 bump 版本或打 tag。官网仍需单独部署，提交或合并
文档不等于已经更新线上网站。

## 10. 文档查询入口

- 在线文档：<https://tom.laofu.online/docs.html>
- 源码仓库：<https://github.com/solos/tom>
- Rust API：<https://docs.rs/tom-agent>、<https://docs.rs/tom-plugin-sdk>

- Package 与扩展作者指南：<https://tom.laofu.online/extension-authoring.md>
- 远程模式：<docs/remote/user-guide.md>
- Rust 扩展与 agent 调试：`tom` 内 `docs` 工具的 `debugging` 主题

当在线文档和已安装版本不一致时，以对应版本的 Git tag 和仓库内文档为准。
