import logging
import os
import re
from pathlib import Path
from typing import Literal

from loguru import logger
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_NUMBER_PATTERN = re.compile(r"(?<![\w.])[+-]?\d+(?:\.\d+)?")


def _validate_loguru_file_option(option: Literal["retention", "rotation"], value: str) -> str:
    """通过 Loguru 公共接口验证文件轮转和保留期表达式。"""
    handler_id: int | None = None
    try:
        if option == "retention":
            handler_id = logger.add(Path(os.devnull), delay=True, rotation="00:00", retention=value)
        else:
            handler_id = logger.add(Path(os.devnull), delay=True, rotation=value)
    except ValueError as exc:
        raise ValueError(f"无效的 Loguru {option} 配置") from exc
    finally:
        if handler_id is not None:
            logger.remove(handler_id)
    return value


def _validate_positive_interval(value: str, field_name: str) -> str:
    """拒绝数字型轮转或保留期中的负数及全零配置。"""
    numbers = [float(number) for number in _NUMBER_PATTERN.findall(value)]
    if any(number < 0 for number in numbers) or (numbers and not any(number > 0 for number in numbers)):
        raise ValueError(f"{field_name} 必须表示正数时间间隔或文件大小")
    return value


class LoggerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file_encoding="utf-8", hide_input_in_errors=True)
    LOG_LEVEL: int = Field(default=logging.INFO, ge=0)  # 从环境变量读取，默认 INFO
    LOG_RETENTION: str = "14 days"
    LOG_ROTATION_TIME: str = "00:00"

    @field_validator("LOG_RETENTION")
    @classmethod
    def validate_retention(cls, value: str) -> str:
        """验证 Loguru 文件保留期并拒绝非正数时长。"""
        _validate_loguru_file_option("retention", value)
        return _validate_positive_interval(value, "LOG_RETENTION")

    @field_validator("LOG_ROTATION_TIME")
    @classmethod
    def validate_rotation(cls, value: str) -> str:
        """验证 Loguru 文件轮转规则并拒绝零或负数间隔。"""
        _validate_loguru_file_option("rotation", value)
        if ":" not in value:
            _validate_positive_interval(value, "LOG_ROTATION_TIME")
        return value


__all__ = ["LoggerSettings"]
