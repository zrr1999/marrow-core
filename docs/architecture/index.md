# 架构概览

marrow-core 是一个**最小化 service/runtime 内核**，遵循严格的核心/演化层隔离原则。

## 设计原则

1. **核心不携带 profile** — 角色树、prompt 策略、model 映射均由外部 profile 仓库提供
2. **单一 CLI 入口** — 所有用户接口通过 `marrow` 命令统一暴露
3. **service-only 定位** — 核心只负责运行时调度，不涉及任务队列或工作项契约

## 关键模块

| 模块 | 职责 |
|------|------|
| `contracts.py` | 运行时清单与工作目录拓扑规则 |
| `heartbeat.py` | 按配置的顶层 agent 执行调度编排 |
| `runtime.py` | socket、队列、二进制路径解析 |
| `ipc.py` | 通过 Unix socket 实现本地控制平面 |
| `services.py` | launchd/systemd 服务描述渲染 |
| `health.py` | doctor 和自检健康检查 |
| `scaffold.py` | 工作目录脚手架与起始配置生成 |
| `prompting.py` | context 执行与 prompt 组装 |

## Prompt 层模型

```
外部 profile rules/        ← 稳定的全局策略
外部 profile roles/        ← 规范角色定义与委托边界
外部 profile context.d/    ← 动态队列、状态、环境事实
skills/                    ← prompt 层契约之外的可复用过程
```

仓库根目录的 `agents/` 已退役，不要在其中添加 prompt 内容。

## 边界示意

```
┌─────────────────────────────────────────────────────┐
│                   外部 profile 仓库                  │
│  (marrow-bot, roles/, rules/, context.d/, skills/)  │
└──────────────────────────┬──────────────────────────┘
                           │ --config 传入
┌──────────────────────────▼──────────────────────────┐
│                    marrow-core                       │
│  heartbeat ← contracts ← runtime ← ipc              │
│  services  ← health   ← scaffold ← prompting        │
└──────────────────────────────────────────────────────┘
```

更多细节见 [Service 边界](service-boundary.md) 和 [Profile 所有权](profile-ownership.md)。
