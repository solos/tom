# pi 兼容 RPC 命令

`tom --mode rpc` 的命令集是 pi RPC 参考的超集。ready 帧中的
`parityComplete` 表示 **pi 基线的每一条命令都已实现**，该标志由
`PI_BASELINE_COMMANDS` 与 `SUPPORTED_COMMANDS` 的差集计算得出，并有单元测试守护，
不会与实现脱节。

```json
{"type":"ready","protocol":"tom","parityComplete":true,"supportedCommands":[...]}
```

## 命令总览

pi 基线 33 条：

| 分类 | 命令 |
| --- | --- |
| 提示 | `prompt`、`steer`、`follow_up` |
| 队列 | `clear_queue`、`set_steering_mode`、`set_follow_up_mode` |
| 运行控制 | `abort`、`abort_bash`、`abort_retry`、`bash` |
| 模型 | `set_model`、`cycle_model`、`get_available_models` |
| 思考等级 | `set_thinking_level`、`cycle_thinking_level`、`get_available_thinking_levels` |
| 会话 | `new_session`、`switch_session`、`clone`、`fork`、`set_session_name` |
| 查询 | `get_state`、`get_commands`、`get_messages`、`get_entries`、`get_tree`、`get_fork_messages`、`get_last_assistant_text`、`get_session_stats` |
| 压缩与重试 | `compact`、`set_auto_compaction`、`set_auto_retry` |
| 导出 | `export_html` |

tom 另有 24 条扩展命令（`get_history`、`get_queue`、`queue_message`、
`cancel_queued`、`navigate`、`append_entry`、`get_session_branch`、
`get_message_summaries`、`get_message_window`、`resume_pending`、
`get_available_tools`、`set_active_tools`、`configure_file_io`、
`file_io_response`、`configure_external_tools`、`external_tool_response`、
`ui_dialog_response`、`get_auth_status`、`oauth`、`set_api_key`、
`execute_command`、`get_stats`、`ping`、`stop`）。

## 关键语义

### steer 与 follow_up

```json
{"id":1,"type":"steer","message":"改走另一条路"}
{"id":1,"type":"follow_up","message":"做完后顺便总结"}
```

两者都返回 `data.disposition: "queued"` 与分配到的 `entryId`。

- `steer` 在当前 assistant 轮次执行完工具调用后、下一次模型调用前投递。
- `follow_up` 只在 agent 完全停止后投递。

与 `prompt` 不同，它们只接受纯文本 `message`：它们作为用户轮次插入运行中，
不携带图片或内容块。

### set_steering_mode / set_follow_up_mode

```json
{"type":"set_steering_mode","mode":"all"}
```

`all` 一次投递全部排队消息，`one-at-a-time`（默认）每轮投递一条。切换只改变
排空规则，已排队的消息保持排队。`Context` 队列不参与该模式，命令对它是空操作。

### set_auto_compaction / set_auto_retry

```json
{"type":"set_auto_compaction","enabled":false}
{"type":"set_auto_retry","enabled":false}
```

运行期生效，作用于下一次操作而非打断进行中的操作。效果可直接从
`get_session_stats` 的 `data.context.compactionEnabled` 观察到。

`set_auto_retry` 只切换开关；重试间隔与次数上限来自 `settings.json` 的 `retry`
块，不属于按会话调整的范围。

### abort_retry 与 abort 的区别

```json
{"type":"abort_retry"}
```

`abort_retry` 只取消正在等待的重试延时，**失败的那次尝试仍是本次操作的结果**，
运行不会因为缺少结果而进入恢复流程。返回 `data.aborted` 表示当时是否有操作在跑。

`abort` 则会中止整个运行。客户端在中断重试后仍想保留已产生的输出时，应使用
`abort_retry`。

### cycle_model / cycle_thinking_level

按目录顺序或模型支持的等级列表轮转一格，返回新值；只有一项时返回 `data: null`
（与参考实现一致），表示无可轮转。

### 会话类命令

`new_session`、`switch_session`、`clone`、`fork` 都返回
`data.cancelled`（当前实现恒为 `false`：tom 尚未提供可取消切换的扩展事件）。

- `new_session` 在同一会话目录下建立空会话。
- `switch_session` 需要 `sessionPath`（会话 id 或文件）；找不到时报错。
- `clone` 在当前位置复制当前会话。
- `fork` 需要 `entryId`，复制会话后**把 leaf 移动到该消息**。不带摘要生成，
  与 `/fork` 的默认行为一致。

以上都需要持久化会话目录；内存会话下无法 fork/clone。

### bash 与 abort_bash

```json
{"id":1,"type":"bash","command":"cargo test"}
```

这是客户端的 `!` 命令，**不是**模型工具调用：输出回到客户端，不进入会话记录。
命令在独立任务中执行，因此 `abort_bash` 可以中途到达。

非零退出不是协议错误，响应形如：

```json
{"data":{"output":"...","error":"Command exited with code 1"}}
```

用户需要先看到状态与已产生的输出。被取消时响应带 `"cancelled":true`。

### export_html

```json
{"type":"export_html","outputPath":"session.html"}
```

相对路径按会话工作目录解析；省略时写入 `session-<timestamp>.html`。响应返回
最终绝对路径。

### get_tree / get_entries / get_fork_messages

- `get_tree` 返回 `{nodes, leafId, count}`，每个节点含 `id`、`parentId`、`seq`、
  `type`、`label`、`isLeaf`，供 `/tree` 类界面渲染。
- `get_entries` 返回当前分支的原始条目（`limit` 上限 500，取最新的一段）。
- `get_fork_messages` 列出可作为 fork 起点的用户消息，含 `entryId`、`text`、`seq`。

### get_session_stats

聚合 `messageCount`、`cachedTokens`、`uncachedTokens`、`totalTokens`、`cost`、
`name`、`leafId`，并内联 `context`（含 `tokens`、`window`、`threshold`、
`percent`、`reserveTokens`、`keepRecentTokens`、`compactionEnabled`、
`estimated`、`trailingTokens`）。

## 兼容性说明

- `parityComplete: true` 只陈述**命令集覆盖**，不表示事件流、字段级语义与 pi
  逐字节相同。差异仍在 `semantics`、`promptContent`、`fileIO` 等能力块中显式声明。
- 响应同时带 `success`/`data`（新）与 `status`/`result`（旧），两者同源，
  便于过渡期客户端任一方向读取。
