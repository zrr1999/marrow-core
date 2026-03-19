# 快速入门

## 安装

### 推荐：通过 uvx 运行（无需本地安装）

```bash
uvx marrow-core doctor --config /path/to/runtime-config.toml
uvx marrow-core run --config /path/to/runtime-config.toml
```

### 本地开发安装

```bash
git clone https://github.com/zrr1999/marrow-core
cd marrow-core
uv sync --all-groups
```

## 使用前提

marrow-core 需要一个外部 runtime config（通常由外部 profile 仓库如 `marrow-bot` 提供）。不要在 marrow-core 仓库内放置 profile 资产。

## 典型工作流

### 1. 验证配置

```bash
uvx marrow-core validate --config /path/to/runtime-config.toml
```

### 2. 健康检查

```bash
uvx marrow-core doctor --config /path/to/runtime-config.toml
```

### 3. 脚手架初始化工作目录

```bash
uvx marrow-core scaffold --output-dir ./my-workspace
```

### 4. 渲染系统服务定义

```bash
# 渲染服务描述文件（不自动安装）
uvx marrow-core install \
  --config /path/to/runtime-config.toml \
  --platform auto \
  --output-dir ./service-out
```

### 5. 运行调度器

```bash
# 持续运行
uvx marrow-core run --config /path/to/runtime-config.toml

# 仅执行一轮（调试用）
uvx marrow-core run --once --config /path/to/runtime-config.toml

# 构建 prompt 但不执行（dry run）
uvx marrow-core run --dry-run --config /path/to/runtime-config.toml
```

## 文档本地预览

本项目使用 [zensical](https://zensical.org/) 构建文档。

```bash
# 安装文档依赖
uv sync --group dev

# 本地预览（http://localhost:8000）
just docs

# 构建静态站点
just docs-build
```
