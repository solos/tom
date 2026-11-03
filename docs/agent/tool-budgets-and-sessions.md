# 工具输出预算、长任务会话与声明预算

这一页说明三件与 token 成本直接相关的能力：**工具输出按模型预算截断**、
**`bash` 的长任务会话**、**工具声明的字节预算**，以及配套的**结构化计划**与
**上下文余量查询**。

它们各自解决一个具体问题，可以独立启用。

---

## 1. 工具输出预算：`TruncationPolicy`

`read`、`bash`、`grep`、`find`、`ls` 的输出上限不再是固定常量，而是**模型的属性**。
同一个 `50KB` 在 64k 窗口模型上会一次吃掉近两成预算，在 1M 窗口模型上又小得没用。

### 优先级

1. `models.json` 里该模型的 `truncationPolicy`（显式声明，最高优先）
2. 由 `contextWindow` 推导：约为窗口的 **5%**，钳制在 4k–25k tokens
3. 都没有时退回历史默认：2000 行 / 50 KB

```json
{
  "providers": {
    "gw": {
      "api": "openai-completions",
      "baseUrl": "https://gw.test/v1",
      "models": [
        { "id": "small", "contextWindow": 64000 },
        { "id": "large", "contextWindow": 1000000, "truncationPolicy": { "tokens": 20000 } },
        { "id": "exact", "truncationPolicy": { "bytes": 51200 } }
      ]
    }
  }
}
```

`{"tokens": N}` 与 `{"bytes": N}` 二选一。token 按 `BYTES_PER_TOKEN = 4` 换算，
与压缩阈值使用同一套估算，避免两个子系统对「还剩多少」给出不同答案。

模型目录里未声明 `truncationPolicy` 的模型走第 2 条推导，因此大窗口模型不会
被 50 KB 绑住，小窗口模型也不会被塞进一份读不完的输出。

**溢出内容的去处不变**：超出预算时全文写入临时文件，提示里给出路径。

---

## 2. `bash` 的长任务会话：`session: true`

一次性执行只有两种结局：在超时前结束（输出可能被截断），或者整个重跑一遍。
会话模式把长任务变成**一次启动 + 多次轮询**。

### 启动

```json
{ "command": "cargo build --release", "session": true, "yield_time_ms": 10000 }
```

返回内容里带 `session_id`（例如 `shell-1`）与 `still running` 提示。命令**不会**
等到结束；`yield_time_ms` 到点就把控制权交回。默认 10000 ms。

### 轮询 / 写入 / 关闭

```json
{ "session_id": "shell-1", "yield_time_ms": 30000 }
{ "session_id": "shell-1", "input": "y" }
{ "session_id": "shell-1", "close": true }
```

- 省略 `input`：只读新输出。
- 传 `input`：写入该进程的 stdin（默认补一个换行）。
- `close: true`：终止进程树。

输出按「已读游标」推进，**同一段输出不会被重放**——重复输出等于重复付费。

### PTY：`tty: true`

默认使用普通管道，`cargo build`、`git status` 的行为与以前完全一致。加
`tty: true` 才会分配伪终端，用于进度条、`isatty` 决定的着色、以及必须从终端读
stdin 的程序。PTY 会带来终端语义（`\r\n`、回显、分页器），所以是**显式开启**的。

PTY 目前只在 Unix 上实现；Windows 上会明确报错，而不是给出半可用的 ConPTY。

### 生命周期

- 关闭：`bash_session` 的 `close`，或工具被丢弃（会话随 `bash` 工具一起结束）。
- 空闲回收：超过 30 分钟未交互的会话被清理。
- 并发上限：16 个。开启第 17 个会被拒绝，并提示先关闭一个——否则一个「每条命令
  开一个会话」的模型会为每次调用泄漏一个进程树。
- 单会话输出保留上限 1 MiB，超出部分丢弃并在下次读取时报告丢弃字节数（按 UTF-8
  字符边界裁剪，不会切坏多字节字符）。

---

## 3. 工具声明预算：`toolsBudgetTokens`

每次请求都要重发完整工具声明，这部分成本在模型读到第一个字之前就已产生。工具多
的时候（一个 MCP 服务器挂二十个工具，每个一段描述）它是每轮的固定开销。

```json
{ "toolsBudgetTokens": 6000 }
```

超出预算时**只裁剪描述**：名称与参数 schema 原样保留，因为参数 schema 才是「模型
能不能正确调用」的关键。一个没有描述的工具是不可选择的，那是用能力换 token。
裁剪从最长的描述开始，能停在第一句就停在第一句，否则在词边界截断并留下 `…`。

### 为什么不是 `world-state diff`

Codex 可以只发 `added`/`removed`/`schema_changed`，因为它的传输保留了服务端状态：
上一次响应可寻址，下一轮就有资格省略没变的部分。

tom 不走这条路——每个请求都是 provider-neutral 转录的**无状态重放**
（Responses API 用 `store: false`，Anthropic 发完整 `messages`）。在这个契约下，
省略一份没变的声明不会省下 token，只会让模型看不见那个工具。

真正能省的部分交给 prompt cache：Anthropic 只在**最后一个**立即工具上挂缓存断点，
缓存命中按前缀判定，所以从中间删掉一份没变的 schema 会改变前缀，把本来便宜的缓存
直接打掉。工具列表的顺序因此保持稳定（注册顺序，原地过滤）。

剩下唯一能压缩的就是声明本身，也就是这一节做的事。

`tom_tools::ToolFingerprint` 提供声明集合的指纹与差异，用于**诊断**：两次指纹相同
说明输入侧逐字节一致，正是缓存能命中的条件；不同则指出是哪个工具变了。

---

## 4. 结构化计划：`update_plan`

计划作为**状态**存在，而不是 system prompt 里的一段散文。

```json
{
  "explanation": "porting the parser",
  "plan": [
    { "step": "read the old parser", "status": "completed" },
    { "step": "port the tokenizer", "status": "in_progress" },
    { "step": "port the grammar", "status": "pending" }
  ]
}
```

- 每次调用**整体替换**计划，必须把剩余步骤全部带上。
- 至多一个步骤可以是 `in_progress`，否则拒绝。
- 工具结果会把清单回显给模型，因此计划跨轮可见，直到压缩为止。
- 渲染为 `kind: "plan"` 的计划面板，用户看到的是当前计划而不是一段会被刷走的输出。

这条工具的直接动因写在 `docs/debugging/llm-repetition-forensics.md`：计划只存在于
散文里时，它会随窗口滑出，模型只能从头重建，于是出现 112 轮重复思考。

---

## 5. 上下文余量：`get_context_remaining`

让模型自己问「我还剩多少」。

```
Context usage: ~16000 of 64000 tokens used, ~48000 remaining (75%).
```

无参数。数值来自 harness 的实时投影上下文估算，与压缩阈值的单位一致。模型窗口未
声明时明确回答「剩余未知」，而不是编一个数字。

用途是让模型在发起一次大 `read` 前自己判断该不该先压缩，而不是等宿主的阈值先触发。

---

## 相关设置一览

| 设置项 | 作用 |
| --- | --- |
| `models.json` → `truncationPolicy` | 该模型的工具输出预算 |
| `models.json` → `contextWindow` | 未声明 policy 时据此推导预算 |
| `settings.json` → `toolsBudgetTokens` | 工具声明 payload 的 token 上限 |
| `settings.json` → `shellCommandPrefix` | 每条 bash 命令的前缀 |
| `settings.json` → `shellPath` | 覆盖 bash 工具使用的解释器 |

## 测试入口

```bash
cargo test -p tom-tools --test bash_session      # 会话生命周期、PTY、写 stdin
cargo test -p tom-tools tools_budget             # 声明裁剪与指纹
cargo test -p tom-tools tools::plan              # 计划面板载荷
cargo test -p tom-tools tools::context_budget    # 上下文余量
cargo test -p tom-ai truncation_policy_tests     # 预算推导与钳制
cargo test -p tom-harness --test tools_budget    # 预算真的到达请求
```
