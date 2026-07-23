# 退役与迁移

marrow-core 已于 2026-07-23 退役。其自治运行时由
[Spark](https://github.com/zrr1999/spark) 的 daemon-owned driver runtime
取代；本仓库只保留为历史参考，不再接受新的运行时能力。

## 替代边界

Spark daemon 现在是以下状态的唯一运行时 owner：

- `goal`、`loop`、`repro`、`implement`、`workflow` 和 `session_todo` 的计时；
- generation、下一次 wake、重试次数和当前 invocation；
- 同 session 执行围栏、取消、drain、重启恢复和事件流；
- one-shot wake prompt；
- `/loop fresh` 的隔离执行 session 和回收；
- 旧 goal、loop、repro、implement、workflow 与 TODO 状态的启动迁移。

TUI 和 Cockpit 只发送控制命令、订阅 daemon 状态并展示输出。关闭或重连
前端不会停止 driver，也不会在前端保留补偿 timer。

marrow-core 的多用户 root supervisor 不再迁移。需要 Unix 用户隔离时，每个
用户运行自己的 Spark daemon；不同用户的进程、状态目录和权限仍由操作系统
隔离。

以下运维便利能力不是自治运行时替代的阻塞项，已记录为 Spark 的后续 TODO：

- Linux systemd 安装器；
- 周期 self-check 和更完整的 doctor；
- 独立更新器；
- 外部后台服务托管或明确委托给平台 service manager；
- profile 导入完善；
- 日志保留与清理策略。

在这些能力落地前，可继续使用 systemd、launchd 或其他平台工具管理每用户
Spark daemon 和外部服务，但不要再让 marrow-core 负责同一工作区的调度。

## 迁移步骤

1. 记录现有 marrow-core config、profile root、workspace、agent command、
   heartbeat interval、timeout 和 service unit。
2. 备份工作区以及需要保留的 `runtime/state`、日志和 profile 数据。
3. 安装 Spark，并以原 Unix 用户启动一个 daemon；不要用 root daemon
   代理多个用户。
4. 在 Spark 中注册对应 workspace，并把角色、上下文和任务状态迁移到该
   workspace 的 Spark 状态模型。
5. 使用 `/goal`、`/loop`、`/repro`、`/implement` 或 workflow 控制面启动
   对应 driver。需要每轮清空模型 transcript 的 loop 使用 `/loop fresh`。
6. 确认 daemon 能投影 driver 状态，并观察至少一次成功 invocation 和下一次
   wake/retry 状态。
7. 停止并禁用 marrow-core service，确认没有旧 heartbeat、`sync-once` 或
   self-check 继续触发。
8. 重启 Spark daemon，确认 active driver 被恢复且逾期 wake 只执行一次。

迁移期间禁止让 marrow-core heartbeat 和 Spark driver 同时操作同一 workspace；
这会绕开双方的单 owner 与执行围栏假设。

## 命令与概念映射

| marrow-core | Spark |
| --- | --- |
| 固定 heartbeat | daemon-owned driver wake |
| `wake --prompt` | one-shot driver wake prompt |
| heartbeat retry/backoff | daemon driver generation 与 retry policy |
| `status` | driver/session snapshot 与事件投影 |
| 单用户 worker | 每 Unix 用户一个 Spark daemon |
| 新一轮无历史上下文 | `/loop fresh` |
| root multi-user supervisor | 不迁移；由每用户 daemon 与 OS 权限隔离替代 |

`sync-once`、service unit 渲染、self-check 和 hosted plugins 没有迁移为第二套
Spark executor。它们应由 Spark 的后续运维能力或平台级工具处理。

## 历史文档

本网站其余页面描述 marrow-core 最终版本的配置和命令，仅供迁移旧实例或
理解历史设计。它们不再是新部署建议。
