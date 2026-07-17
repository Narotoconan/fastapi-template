import json
import re
from pathlib import Path
from typing import cast

from config.database_config import DatabaseSettings

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_uvicorn_graceful_timeout() -> int:
    """从 Dockerfile 的 JSON CMD 中读取 Uvicorn 优雅关闭秒数。"""
    dockerfile = (_PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    command_line = next(line for line in dockerfile.splitlines() if line.startswith("CMD "))
    command_value: object = json.loads(command_line.removeprefix("CMD "))
    assert isinstance(command_value, list)
    assert all(isinstance(argument, str) for argument in command_value)
    command = cast(list[str], command_value)
    option_index = command.index("--timeout-graceful-shutdown")
    return int(command[option_index + 1])


def _read_compose_stop_grace_period() -> int:
    """从 Compose 配置读取 API 容器被强制停止前的宽限秒数。"""
    compose = (_PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")
    duration_match = re.search(r"^\s*stop_grace_period:\s*(\d+)s\s*$", compose, flags=re.MULTILINE)
    assert duration_match is not None
    return int(duration_match.group(1))


def test_default_shutdown_budget_is_strictly_increasing() -> None:
    """数据库、Uvicorn 与 Compose 的默认停止预算应逐层留出收尾时间。"""
    database_timeout = DatabaseSettings(DB_PASSWORD="test-password").DB_COMMAND_TIMEOUT
    uvicorn_timeout = _read_uvicorn_graceful_timeout()
    compose_timeout = _read_compose_stop_grace_period()

    assert (database_timeout, uvicorn_timeout, compose_timeout) == (60.0, 70, 90)
    assert database_timeout < uvicorn_timeout < compose_timeout
    assert compose_timeout - uvicorn_timeout >= 20
