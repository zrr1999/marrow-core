# Service 边界

## marrow-core 拥有

- **服务生命周期**：启动、停止、重启调度循环
- **调度**：按配置触发各 agent 的心跳
- **Sync 与自检**：一次性 sync、validate、doctor
- **IPC 控制平面**：通过 Unix socket 查询和控制运行时状态
- **即时触发**：`wake` 命令唤醒 agent（可附带一次性 prompt）
- **服务安装**：渲染 launchd / systemd 服务描述文件
- **脚手架**：初始化工作目录和起始配置

## marrow-core 不拥有

| 职责 | 归属 |
|------|------|
| 任务队列与工作项契约 | `marrow-task` / `loom` |
| 人工工作流状态机 | `loom` |
| 外部工作流编排策略 | 外部 profile |
| 角色树与 prompt 策略 | 外部 profile（如 `marrow-bot`） |
| model 映射与 casting 流程 | 外部 profile + `role-forge` |

## 运行时边界文件

- `marrow_core/contracts.py` — 角色清单与工作目录拓扑
- `marrow_core/heartbeat.py` — 调度编排入口
- `marrow_core/ipc.py` — Unix socket 控制平面
