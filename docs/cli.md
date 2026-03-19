# CLI 参考

marrow-core 暴露单一 `marrow` 命令，所有子命令均围绕 **service/runtime** 定位设计。

## 安装模式与命令可用范围

marrow-core 支持两种使用模式，部分命令仅在 **源码 checkout** 模式下可用：

| 模式 | 说明 | 安装方式 |
|------|------|------|
| **uvx 安装模式**（推荐） | 通过 `uvx marrow-core <cmd>` 调用，无需 clone 源码 | `uvx marrow-core ...` |
| **源码 checkout 模式** | clone 仓库后以 `uv run marrow-core <cmd>` 或直接调用 | `git clone` + `uv run` |

### 源码 checkout 专用命令

以下命令**仅在拥有 marrow-core 源码 checkout 且 config 中 `core_dir` 指向该目录时**才能正常工作：

| 命令 | 原因 |
|------|------|
| `sync-once` | 内部直接调用 `git -C core_dir` 和 `uv sync --directory core_dir`；若 `core_dir` 未指向源码目录则报错退出 |

> **注意**：`sync-once` 是维护型操作，适合维护者在本地 checkout 上手动触发，不适合 uvx 部署的生产运行时。对于纯 uvx 安装环境，应在 config 中禁用 sync（`[sync] enabled = false`）或使用外部 repo 维护流程。

### 支持 uvx 安装的命令

以下命令通过 `uvx marrow-core` 即可直接调用，无需源码 checkout：

| 命令 | 说明 |
|------|------|
| `run` | 启动持续调度服务 |
| `run-once` | 单轮执行后退出 |
| `dry-run` | 构建 prompt，不执行 agent |
| `validate` | 验证配置格式与内容 |
| `doctor` | 检查工作目录与命令健康 |
| `setup` | 初始化运行时目录 |
| `scaffold` | 生成起始工作目录与配置（`--core-dir` 可选，若传入则应指向源码目录） |
| `install-service` | 渲染 launchd/systemd 服务文件 |
| `status` | IPC 查询运行时状态 |
| `wake` | 唤醒指定 agent |

## 命令概览

| 命令 | 分组 | 说明 |
|------|------|------|
| `run` | 调度 | 启动持续调度循环（supervisor 或单用户心跳） |
| `run-once` | 调度 | 每个 agent 执行一次心跳后退出 |
| `dry-run` | 调度 | 构建 prompt 但不运行 agent |
| `sync-once` | 同步 | 执行一次有界 sync 尝试 |
| `validate` | 检查 | 验证配置并打印摘要 |
| `doctor` | 检查 | 检查工作目录与命令健康状态 |
| `setup` | 初始化 | 初始化运行时目录和工作目录 |
| `scaffold` | 初始化 | 创建起始工作目录和配置 |
| `install-service` | 服务 | 渲染服务描述文件（launchd/systemd） |
| `status` | 运行时 | 通过 IPC 查询运行时状态 |
| `wake` | 运行时 | 唤醒 agent，可附带一次性 prompt |

## 详细说明

### `marrow run`

```
marrow run [--config PATH]
```

启动根 supervisor 或单用户心跳循环。会持续运行直到手动终止。

### `marrow run-once`

```
marrow run-once [--config PATH]
```

对每个已配置的 agent 各执行一次心跳后退出。适合调试和 CI。

### `marrow dry-run`

```
marrow dry-run [--config PATH]
```

构建每个 agent 的 prompt 但不实际执行，打印 prompt 摘要。

### `marrow sync-once`

```
marrow sync-once [--config PATH]
```

执行一次有界的 sync 操作（git fetch + merge + uv sync + 服务渲染）。

**⚠ 源码 checkout 专用**：此命令要求 config 中 `core_dir` 指向 marrow-core 源码目录。若 `core_dir` 未配置或路径无效，命令会报错退出。纯 uvx 安装环境应禁用 sync 或使用外部维护流程。

### `marrow validate`

```
marrow validate [--config PATH]
```

验证 runtime config 文件格式和内容，打印配置摘要。不启动任何服务。

### `marrow doctor`

```
marrow doctor [--config PATH]
```

检查工作目录结构、所需命令可用性和运行时健康状态。

### `marrow setup`

```
marrow setup [--config PATH]
```

初始化运行时目录和 agent 工作目录。通常在首次部署时运行。

### `marrow scaffold`

```
marrow scaffold --workspace PATH --config-out PATH [--core-dir PATH] [--source-context-dir PATH] [--profile-root PATH]
```

在指定目录创建起始工作目录和示例配置，方便新部署快速上手。

- `--core-dir`（可选）：若传入，应指向 marrow-core 源码目录；会被写入生成的配置文件中。在纯 uvx 安装环境中通常留空，仅开发/维护者需要填写。
- `--source-context-dir` / `--profile-root`（可选）：从外部 profile 仓库复制 context.d 内容。

### `marrow install-service`

```
marrow install-service [--config PATH] [--platform auto|launchd|systemd] [--output-dir PATH]
```

渲染服务描述文件到 `--output-dir`，不自动安装。支持 macOS launchd 和 Linux systemd。

### `marrow status`

```
marrow status [--config PATH]
```

通过 Unix socket IPC 查询当前运行时状态（需要服务正在运行）。

### `marrow wake`

```
marrow wake [--agent AGENT_ID] [--prompt TEXT] [--config PATH]
```

唤醒指定 agent，可附带一次性 prompt 覆盖默认心跳行为。
