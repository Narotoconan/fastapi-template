# syntax=docker/dockerfile:1.7
# Dockerfile 1.7 启用下方 RUN --mount 使用的 BuildKit 缓存挂载语法。

# 从固定版本镜像提取 uv/uvx，避免在构建阶段通过网络脚本安装包管理器。
FROM ghcr.io/astral-sh/uv:0.11.28 AS uv

# builder 与 runtime 使用相同的 Python/Debian 基础，确保复制虚拟环境时 ABI 保持兼容。
FROM python:3.12-slim-bookworm AS builder

COPY --from=uv /uv /uvx /bin/

# 预编译依赖字节码以缩短冷启动；缓存挂载与镜像层通常不在同一文件系统，使用 copy 避免硬链接问题；
# 基础镜像已提供 Python，禁止 uv 额外下载解释器。
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# 先复制依赖清单，使业务源码变化时仍可复用依赖安装层缓存。
COPY pyproject.toml uv.lock ./

# 下载缓存只用于加速后续构建，不会写入镜像层；严格按锁文件安装生产依赖，不安装开发组和项目源码本身。
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project


# 最终镜像不包含 uv、构建缓存和编译工具，只保留运行所需文件。
FROM python:3.12-slim-bookworm AS runtime

# 默认使用复制来的虚拟环境；运行期禁止写入新的 .pyc，让容器日志立即输出，并固定使用北京时间。
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

# 固定非 root UID/GID，便于宿主机为 logs 绑定目录预先配置一致的文件权限；nologin 禁止交互式登录。
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-log-init --create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app app ./app
COPY --chown=app:app config ./config
COPY --chown=app:app main.py pyproject.toml ./

# 文件日志目录必须由运行用户可写；Compose 会把宿主机 ./logs 绑定到该路径。
RUN mkdir -p /app/logs && chown app:app /app/logs

# 从这里开始的运行时进程均使用最低权限账户。
USER app

# 仅声明容器监听端口，不会自动发布到宿主机；实际映射由 Compose 的 API_PORT 控制。
EXPOSE 8000

# 使用 Python 标准库避免为健康检查额外安装 curl；请求内部超时 3 秒，小于 Docker 外层 5 秒。
# /health 同时检查 PostgreSQL 和 Redis，任一关键依赖不可用都会使容器进入 unhealthy 状态。
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

# SIGTERM 可让 Uvicorn 执行 lifespan 清理逻辑；默认停止预算为：
# DB 单条命令 60 秒 < Uvicorn 优雅关闭 70 秒 < Compose 强制停止 90 秒。
STOPSIGNAL SIGTERM

# 容器内监听所有网卡，宿主机暴露范围由 Compose 端口映射决定。
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "70"]
