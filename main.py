# 1.初始化配置
from config.settings import get_settings

settings = get_settings()

# 2.加载日志模块
from app.core.log import register_log

register_log()

# 3.启动server
from fastapi import FastAPI
from app.api import register_router
from app.core.events import lifespan
from app.core.rate_limit import register_rate_limiter
from app.exceptions import register_exception_handlers
from app.middlewares import register_middlewares

app = FastAPI(title=settings.app.APP_NAME, version=settings.app.APP_VERSION, lifespan=lifespan)
# 3.1注册全局异常处理器
register_exception_handlers(app)
# 3.2注册接口速率限制
register_rate_limiter(app)
# 3.3注册默认中间件（CORS → GZip；JWT 当前未启用）
register_middlewares(app)
# 3.4注册路由
register_router(app)
