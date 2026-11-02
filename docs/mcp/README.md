# MCP 服务器

`tom` 实现了 [Model Context Protocol](https://modelcontextprotocol.io) 客户端：
连接 MCP 服务器，把它们暴露的工具变成模型可直接调用的工具，工具名格式为
`mcp__<服务器名>__<工具名>`。

范围是有意收窄的。`tom` 复用 MCP 的**工具**生态，但不做 MCP 宿主：
resources、prompts、sampling、elicitation 和 roots 都不支持。客户端握手只声明
工具能力，因此合规的服务器不会发来本客户端必须拒绝的请求。

## 快速开始

```bash
# 添加一个本地 stdio 服务器
tom mcp add filesystem --command npx --arg -y --arg @modelcontextprotocol/server-filesystem --arg .

# 添加一个远程 HTTP 服务器
tom mcp add docs --url https://example.com/mcp --header "Authorization: Bearer ${DOCS_TOKEN}"

# 连接并查看工具
tom mcp list
```

`tom mcp list` 会真正连接每个启用的服务器，打印状态与工具列表；任一服务器
连接失败时命令以 1 退出。`tom mcp status` 只读配置、不联网。

## 配置文件

配置来自两个文件，格式与其它 MCP 客户端一致，可直接拷贝 `mcpServers` 段：

| 位置 | 说明 |
| --- | --- |
| `~/.tom/agent/mcp.json` | 用户级服务器 |
| `.tom/mcp.json` | 项目级服务器，**仅在该项目受信任时读取** |

同名条目中，项目级覆盖用户级。

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]
    },
    "docs": {
      "url": "https://example.com/mcp",
      "headers": { "Authorization": "Bearer ${DOCS_TOKEN}" },
      "description": "搜索并阅读产品文档"
    }
  }
}
```

`command` 选择 stdio，`url` 选择 streamable HTTP。字段：

| 字段 | 说明 |
| --- | --- |
| `command` / `args` | stdio 可执行文件与其参数。`command` 是单个可执行文件，不是 shell 命令串 |
| `env` | stdio 子进程的额外环境变量，值支持 `${VAR}` |
| `cwd` | stdio 工作目录；相对路径按项目根解析，`~/` 表示家目录 |
| `url` / `headers` | HTTP 端点与额外请求头，头值支持 `${VAR}` |
| `description` | 一句话说明，会出现在工具描述前缀里，便于区分同名工具 |
| `exposure` | `direct`（默认）或 `deferred`。`deferred` 把该服务器的工具留在注册表里但**不声明给模型**，只能由 `tool_search` 检索加载 |
| `timeout` | 单次请求超时秒数，默认 60 |
| `enabled` | `false` 保留条目但不连接 |
| `type` | 可选，必须是 `stdio` / `http` / `streamable-http`。`sse` 被拒绝 |

### 部分覆盖

一个项目级条目若**不带** `command`/`url`/`type`，就只是对用户级同名服务器的
局部覆盖：只改变 `enabled`、`description`、`timeout`，其余（含 `env`、
`headers`）继承。这是在单个项目里关掉某个服务器的标准写法：

```json
{ "mcpServers": { "internal-tools": { "enabled": false } } }
```

## 工具膨胀：`exposure` 与 `tool_search`

每连接一个服务器，声明给模型的工具就多几条。工具数量到几十条时，全量声明会
占掉可观的上下文，并降低模型的选择准确率——这是 MCP 落地后立刻会遇到的问题。

`tool_search` 是一个按需检索工具：它用 BM25 在**未声明**的工具元数据（名称、
描述、参数 schema 的属性名与说明）上排序，把命中的工具加入 active 集合。加载结果
会写成一条 `active_tools_change` 条目，因此在 `/tree`、续接会话与 fork 之后仍然
生效；同一次运行的下一轮请求就会声明它们（不是等到下一次 prompt）。

`exposure` 决定一个服务器的工具走哪条路：

| 值 | 行为 | 适用 |
| --- | --- | --- |
| `direct`（默认） | 和其它内置工具一样声明给模型 | 小工具集、常用 |
| `deferred` | 注册但不声明，只能由 `tool_search` 加载 | 大服务器（filesystem 有 10+ 工具） |

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
      "exposure": "deferred"
    }
  }
}
```

默认是 `direct`，因为延迟声明是**权衡而非白赚**：deferred 工具在可用之前要额外花
一次 `tool_search` 调用。工具少的服务器直接声明更划算，所以延迟是按服务器逐个
开启的。项目级条目可以只写 `"exposure": "deferred"` 覆盖用户级同名服务器。

只要 MCP 贡献了任何工具，`tool_search` 就会注册并激活；没有 MCP 时会话的工具集
不变，不多花 token。

## 工具命名

Provider 的工具名只允许 `[A-Za-z0-9_-]`，因此其它字符会被替换为 `_`。若替换
真的丢失了信息，会追加确定性哈希后缀，避免 `my-tools` 与 `my_tools` 撞名。

工具描述会加上服务器前缀，例如
`MCP tool from server \`docs\`: 搜索产品文档`。

## 失败语义

- **一个坏服务器不影响其它服务器。** 配置错误与连接失败按服务器汇报，其余照常
  加载。
- **工具错误是结果，不是中止。** 服务器返回的错误会作为文本交给模型，让它自行
  调整；只有传输层已关闭才会中止（否则每个剩余工具调用都会各超时一次）。
- **子进程随宿主退出。** stdio 服务器以 `kill_on_drop` 启动并在 drop 时显式
  终止，不会留下孤儿进程占着端口或文件锁。
- **stderr 始终被排空。** 否则日志量大的服务器会写满管道缓冲区并把自己阻塞。

## 与扩展的关系

MCP 工具在扩展工具之后合并，因此同名时扩展工具被 MCP 工具覆盖（与
`--tools`/`--exclude-tools` 策略一致）。`--no-extensions` 同时关闭 MCP：从用户
角度看两者都是「外部工具」。

## 限制

- 不支持 SSE 传输（仅 stdio 与 streamable HTTP）。
- 不支持 resources、prompts、sampling、elicitation、roots。
- 不支持 OAuth 登录流程；需要认证的 HTTP 服务器请通过 `headers` 传令牌。
- `tool_search` 的检索是词法的（BM25），没有同义词表：`tickets` 找不到
  `issues`。它也不做 embedding，因此没有索引需要随服务器连接/断开而重建。
