# Profile 所有权

## 原则

marrow-core **不携带**任何默认 profile 资产。所有 profile 内容由外部仓库提供。

## Profile 资产归属

| 资产 | 归属位置 | 说明 |
|------|----------|------|
| `roles/` | 外部 profile 仓库 | 规范角色定义与委托边界 |
| `roles.toml` | 外部 profile 仓库 | model 层级映射与元数据 |
| `rules/` | 外部 profile 仓库 | 稳定的全局策略 |
| `context.d/` | 外部 profile 仓库 | 动态队列、状态、环境事实 |
| `skills/` | 外部 profile 仓库 | prompt 层契约之外的可复用过程 |

## 已退役的资产

以下资产已从 marrow-core 迁移至外部仓库，**不要**在 marrow-core 中重新添加：

- `lib.sh` / `setup.sh`
- `context.d/`
- `prompts/`
- `marrow.toml`
- `roles.toml`
- 仓库根目录的 `agents/`

## 部署模式

```bash
# 外部 profile 通过 role-forge 渲染后传给 marrow-core
uvx role-forge cast --profile /path/to/marrow-bot

# 将渲染结果的路径传给 marrow-core
uvx marrow-core run --config /path/to/runtime-config.toml
```

参考：[快速入门](../quickstart.md) | [Service 边界](service-boundary.md)
