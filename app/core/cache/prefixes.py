"""
Redis 缓存键前缀定义

业务模块的缓存键名管理，确保键名结构统一
格式: {PROJECT_PREFIX}:{MODULE}:{SUB_KEY}:{RESOURCE_ID}

示例:
  anda_erp:user:profile:1
  anda_erp:order:pending:O001
  anda_erp:payment:invoice:INV001
"""


class RedisPrefixes:
    """业务模块缓存键前缀常量"""

    # ==================== 用户模块 ====================
    USER_PROFILE = "user:profile"
    """用户档案信息

    使用示例:
        key = f'{RedisPrefixes.USER_PROFILE}:1'
        await redis.set(key, user_data)
        # Redis 中: anda_erp:user:profile:1
    """

    USER_SETTINGS = "user:settings"
    """用户设置"""

    USER_PERMISSIONS = "user:permissions"
    """用户权限"""

    USER_SESSIONS = "user:sessions"
    """用户会话"""

    # ==================== 库存模块 ====================
    INVENTORY_STOCK = "inventory:stock"
    """库存数量"""

    INVENTORY_RESERVED = "inventory:reserved"
    """预留库存"""

    # ==================== 报表模块 ====================
    REPORT_DAILY = "report:daily"
    """日报"""

    REPORT_MONTHLY = "report:monthly"
    """月报"""

    REPORT_SUMMARY = "report:summary"
    """汇总报表"""

    # ==================== 配置/缓存 ====================
    CONFIG_APP = "config:app"
    """应用配置"""

    CONFIG_PRODUCTS = "config:products"
    """产品配置"""

    CACHE_TRENDING = "cache:trending"
    """热门数据缓存"""


__all__ = ["RedisPrefixes"]
