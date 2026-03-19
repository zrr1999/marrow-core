# marrow-core

**最小化自演化 agent 调度器，严格隔离核心与演化层。**

marrow-core 是一个纯粹的 service/runtime 内核，负责 agent 调度、服务生命周期和运行时自检。它不携带默认配置文件、角色树或 casting 流程——这些均由外部 profile 仓库（如 `marrow-bot`）提供。

## 核心职责

| 职责 | 说明 |
|------|------|
| 服务生命周期 | `run` / `run --once` / `run --dry-run` 调度心跳循环 |
| 调度 | 按配置触发各 agent 的心跳 |
| Sync 与自检 | `sync-once`、`validate`、`doctor` |
| IPC 状态控制 | 通过 Unix socket 查询和控制运行时 |
| 即时触发 | `wake` 唤醒 agent（可附带一次性 prompt）|
| 服务安装 | `install` 渲染 launchd / systemd 服务描述文件 |

## 不包含的内容

- 任务队列与工作项契约 → 见 `marrow-task`
- 人工工作流状态机 → 见 `loom`
- 角色树与 prompt 策略 → 见外部 profile（`marrow-bot`）

## 快速开始

```bash
# 部署前健康检查
uvx marrow-core doctor --config /path/to/runtime-config.toml

# 以服务方式运行
uvx marrow-core run --config /path/to/runtime-config.toml

# 渲染服务描述文件（不自动安装）
uvx marrow-core install --config /path/to/runtime-config.toml --platform auto --output-dir ./service-out
```

更多内容请见 [快速入门](quickstart.md) 和 [CLI 参考](cli.md)。
