# 项目开发规范 (Copilot Instructions)

## 1. 技术栈上下文
- **语言/框架**: Python 3.12, FastAPI
- **目录结构**: 遵循标准的 app/ 架构，项目配置位于config/，业务逻辑位于 app/services
- **包管理器**: 项目使用UV进行包管理，在项目的虚拟环境中运行

## 2. 核心编码规范
### 日志处理 (Logging)
- **禁止**: 严禁使用 `print()` 或原生 `logging` 库。
- **规范**: 必须使用项目封装的统一日志工具。
- **导入**: `from app.core.log import log`
- **用法**: 仅允许使用 `log.info()`, `log.error()`, `log.warning()`, `log.debug()`

### 异常处理 (Exception Handling)
- 业务异常需抛出 `app.core.exceptions` 中的自定义异常。
- 必须包含具体的错误原因描述。

### 字符串模板输出处理
- 在打印输出时，优先使用f-string风格的字符串模板，尽量避免使用字符串拼接或其他格式化方式。

## 3. 命名与注释
- 函数必须包含 类型提示 (Type Hints)。
- 关键业务逻辑必须编写中文 docstring。

## 4. 代码风格 (Ruff)
- **工具**: 项目使用 [Ruff](https://docs.astral.sh/ruff/) 进行代码检查（Lint）与格式化（Format），配置位于 `pyproject.toml` 的 `[tool.ruff]` 节。
- **执行**: `uv run ruff check .` 检查；`uv run ruff format .` 格式化；不可直接执行`uv run ruff check . --fix` 自动修复，--fix允需人工手动处理。
- **生成代码必须通过 Ruff 检查**，不得引入新的 Lint 错误。

### 关键规则说明
| 规则 | 要求 |
|------|------|
| `T201` | 禁止使用 `print()`，使用 `log.*` 替代 |
| `TID251` | 禁止 `import logging`，使用 `from app.core.log import log` |
| `I` (isort) | import 必须分组排序：标准库 → 第三方库 → 项目内部包（`app`/`config`） |
| `UP` (pyupgrade) | 遵循 Python 3.12 新写法，如用 `collections.abc.Callable` 替代 `typing.Callable` |

### 例外说明
- `app/core/log/*.py` 和 `config/logger_config.py`：允许 `import logging`（日志基础设施本身需要操作原生 logging）。
- `main.py`：允许非顶部导入（启动初始化顺序有意为之）。
