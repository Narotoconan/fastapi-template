import logging
import sys

from loguru import logger

from config.settings import get_settings


def register() -> logging.Logger:
    settings = get_settings()
    level = settings.logger.LOG_LEVEL
    path = f"{settings.app.BASE_PATH}/logs"
    retention = settings.logger.LOG_RETENTION
    rotation_time = settings.logger.LOG_ROTATION_TIME

    # ✅ 移除 loguru 的默认 handler（重要！）
    logger.remove()

    # 拦截根记录器
    logging.root.handlers = [InterceptHandler()]
    logging.root.setLevel(level)

    # 清理其他记录器的处理程序
    for name in logging.root.manager.loggerDict.keys():
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True

    # 配置 loguru - 添加格式化
    logger.add(
        sink=sys.stdout,
        level=level,
        enqueue=True,  # ✅ 异步处理，不阻塞主线程
    )
    logger.add(
        sink=f"{path}/app.log",
        level=level,
        rotation=rotation_time,
        retention=retention,
        enqueue=True,  # ✅ 异步处理，不阻塞主线程
    )

    return logger


class InterceptHandler(logging.Handler):
    def emit(self, record):
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


__all__ = ["register"]
