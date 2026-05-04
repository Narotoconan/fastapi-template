"""
Pydantic v2 校验错误 中文国际化翻译器

职责:
    - 将 Pydantic v2 原始 error dict 的 type 字段映射为中文错误消息
    - 支持携带上下文参数 (ctx) 的动态消息
    - 将字段路径 (loc) 格式化为可读的中文字段名
"""

from collections.abc import Callable

# ==================== 字段路径格式化 ====================

# 请求来源位置前缀，格式化时跳过
_LOC_PREFIXES = {"body", "query", "path", "header", "cookie"}


def format_field_loc(loc: tuple[str | int, ...]) -> str:
    """
    将 Pydantic loc 元组格式化为可读字段路径。

    示例:
        ("body", "username")          → "username"
        ("body", "address", "city")   → "address.city"
        ("body", "items", 0, "name")  → "items[0].name"
        ("query", "page")             → "page"
    """
    parts: list[str | int] = list(loc)
    # 跳过来源前缀
    if parts and str(parts[0]) in _LOC_PREFIXES:
        parts = parts[1:]

    if not parts:
        return ""

    # 修复: 避免与内置名 result 冲突，使用 path 作为变量名
    path = str(parts[0])
    for part in parts[1:]:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


# ==================== 错误消息映射表 ====================

# value: str                    → 静态消息
# value: Callable[[dict], str]  → 动态消息，接收 ctx dict，返回 str
_ERROR_TYPE_MAP: dict[str, str | Callable[[dict], str]] = {
    # ----- 必填 -----
    "missing": "该字段为必填项",
    # ----- 类型错误 -----
    "string_type": "必须是字符串类型",
    "int_type": "必须是整数类型",
    "float_type": "必须是数字类型",
    "bool_type": "必须是布尔类型",
    "list_type": "必须是列表类型",
    "set_type": "必须是集合类型",
    "tuple_type": "必须是元组类型",
    "dict_type": "必须是对象类型",
    "none_required": "该字段必须为空",
    "bytes_type": "必须是字节类型",
    # ----- 解析失败 -----
    "int_parsing": "无法解析为整数，请检查输入格式",
    "float_parsing": "无法解析为数字，请检查输入格式",
    "bool_parsing": "无法解析为布尔值，请传入 true 或 false",
    "int_from_float": "不允许传入浮点数，请传入整数",
    # ----- 字符串长度 -----
    "string_too_short": lambda ctx: f"长度不能少于 {ctx.get('min_length', '?')} 个字符",
    "string_too_long": lambda ctx: f"长度不能超过 {ctx.get('max_length', '?')} 个字符",
    # ----- 字节长度 -----
    "bytes_too_short": lambda ctx: f"字节长度不能少于 {ctx.get('min_length', '?')}",
    "bytes_too_long": lambda ctx: f"字节长度不能超过 {ctx.get('max_length', '?')}",
    # ----- 数值范围 -----
    # 修复: gt(严格大于) 与 ge(大于等于) 语义不同，必须区分表达
    "too_small": lambda ctx: (
        f"值不能小于 {ctx['ge']}"
        if ctx.get("ge") is not None
        else f"值必须大于 {ctx['gt']}"
        if ctx.get("gt") is not None
        else "值过小，超出允许范围"
    ),
    # 修复: lt(严格小于) 与 le(小于等于) 语义不同，必须区分表达
    "too_big": lambda ctx: (
        f"值不能大于 {ctx['le']}"
        if ctx.get("le") is not None
        else f"值必须小于 {ctx['lt']}"
        if ctx.get("lt") is not None
        else "值过大，超出允许范围"
    ),
    "multiple_of": lambda ctx: f"必须是 {ctx.get('multiple_of', '?')} 的倍数",
    "finite_number": "必须是有效数字（不能为无穷大或 NaN）",
    # ----- 正则/格式 -----
    "string_pattern_mismatch": "格式不正确，请检查输入内容",
    # ----- 枚举 / 字面量 -----
    # 不透传 ctx["expected"]，避免将内部枚举值/字面量约束暴露给客户端
    # 合法值信息应由 OpenAPI 文档（/docs）承载，而非错误响应
    "enum": "参数值不合法，请传入有效选项",
    "literal_error": "参数值不合法，请传入有效选项",
    # ----- JSON -----
    "json_invalid": "必须是合法的 JSON 格式",
    "json_type": "必须是合法的 JSON 格式",
    # ----- URL -----
    "url_type": "必须是合法的 URL 地址",
    "url_parsing": "URL 格式不正确",
    "url_scheme": lambda ctx: f"URL 协议必须为: {ctx.get('expected_schemes', '?')}",
    # ----- 日期 / 时间 -----
    "datetime_type": "必须是合法的日期时间格式",
    "datetime_parsing": "日期时间格式不正确",
    "date_type": "必须是合法的日期格式",
    "date_parsing": "日期格式不正确",
    "time_type": "必须是合法的时间格式",
    "time_parsing": "时间格式不正确",
    # ----- UUID -----
    "uuid_type": "必须是合法的 UUID 格式",
    "uuid_parsing": "UUID 格式不正确",
    # ----- 类型实例 -----
    "is_instance_of": lambda ctx: f"必须是 {ctx.get('class', '?')} 类型的实例",
    # ----- 自定义校验器 / 通用值错误 -----
    # 修复: 自定义 validator raise ValueError("msg") 时，msg 存于 ctx["error"]，
    #       应优先透传该消息，而非返回死板的通用提示
    "value_error": lambda ctx: str(ctx["error"]) if ctx.get("error") else "数据不合法，请检查输入内容",
    "assertion_error": lambda ctx: str(ctx["error"]) if ctx.get("error") else "数据校验未通过",
}

_DEFAULT_MESSAGE = "参数校验失败，请检查输入内容"


# ==================== 对外翻译接口 ====================


def translate_validation_error(error: dict) -> str:
    """
    将单条 Pydantic v2 error dict 翻译为中文消息字符串。

    :param error: Pydantic errors() 列表中的单条 error dict
    :return: 格式为 「{field}: {中文消息}」 或 「{中文消息}」（无字段时）
    """
    error_type: str = error.get("type", "")
    ctx: dict = error.get("ctx", {})
    loc: tuple[str | int, ...] = error.get("loc", ())

    # 获取中文消息
    handler = _ERROR_TYPE_MAP.get(error_type, _DEFAULT_MESSAGE)
    if callable(handler):
        try:
            cn_message = handler(ctx)
        except Exception:
            cn_message = _DEFAULT_MESSAGE
    else:
        cn_message = handler

    # 拼接字段路径
    field = format_field_loc(loc)
    return f"{field}: {cn_message}" if field else cn_message


__all__ = ["format_field_loc", "translate_validation_error"]
