# AGENTS.md

## 适用范围

本文件用于指导 Codex 在本 FastAPI 仓库中工作，默认适用于仓库根目录及所有子目录。
如果子目录存在更具体的 `AGENTS.md`，以更靠近当前工作目录的说明为准。
目标：生成、修改和审查代码时，保持项目架构、异步模式、日志、异常和质量门禁一致。

## 项目上下文

* 语言与框架：Python 3.12、FastAPI。
* 包管理器：使用 `uv`，命令默认通过 `uv run ...` 执行。
* Web、数据库、缓存、限流及其他外部网络 I/O 默认使用异步模式。
* ORM：SQLAlchemy 默认使用异步方式，例如 `AsyncSession`、`async with`、`await session.execute(...)`。
* 项目配置位于 `config/`。
* 应用主体位于 `app/`。
* 路由/API 位于 `app/api/`。
* 请求、响应和数据校验模型位于 `app/schemas/`。
* 依赖注入位于 `app/dependencies/`。
* 业务逻辑优先放在 `app/services/`。
* 数据库操作位于 `app/repositories/`。
* 异常定义与异常处理器位于 `app/exceptions/`。
* 日志、数据库、缓存、限流等基础能力位于 `app/core/`。
* 项目枚举类型数据位于 `app/enums/`。公共枚举类型可放在 `app/enums/common.py`，业务相关枚举类型可放在 `app/enums/xxx.py`。
* 定时任务相关逻辑位于 `app/scheduler/`。
* 项目总体分三层：路由层（router）、服务层（service）、数据访问层（repository）。

## Codex 工作原则

* 修改前先阅读相关代码、配置、调用链和测试，不要只根据文件名猜测实现。
* 修改前先查看 `git status`，识别并保护用户已有改动；不要覆盖、回滚或格式化无关改动。
* 优先做最小必要变更，不要顺手重构无关代码。
* 遵循现有项目风格；如果现有代码与本文件冲突，以本文件的硬性规则为准。
* 不要擅自新增大型依赖、替换技术栈或改变公共接口。
* 不确定业务规则时，先从代码、测试、README、配置中寻找依据；仍不确定时在最终回复中说明假设。
* 不要修改真实环境文件（`.env`、`.env.*`）、生产配置、凭证或敏感信息；`.env.example` 仅在用户明确要求时修改，且不得写入真实值。

## 架构约定

* 路由层保持轻量：负责参数接收、依赖注入、权限入口和响应组装。
* 复杂业务逻辑放在 service 层，不要堆在 router 中。
* 数据访问遵循项目现有模式，不要在 router 中直接编写复杂查询。
* Pydantic 模型用于请求、响应和数据校验，命名和目录遵循现有项目习惯。
* 新增接口应明确 request schema、response schema、权限依赖和异常场景。
* JSON API 默认使用 `ResponseSchema` / `PageResponseSchema`；文件下载、流式响应等场景可以直接返回 `StreamingResponse` / `FileResponse`，但错误响应仍应保持统一。
* 不要为了单个 JSON 接口引入不一致的响应格式。
* 修改公共接口、数据库结构、权限逻辑或异常结构时，同步检查调用方、测试和文档。

## 异步开发规范

* FastAPI 接口默认使用 `async def`。
* service、Repository 与 `app/core/` 基础设施中涉及 I/O 的函数默认使用异步定义。
* SQLAlchemy 默认使用异步会话，不要在异步调用链中混用同步 `Session`。
* 数据库操作必须正确使用 `await`。
* Redis 缓存、接口限流和 HTTP 客户端默认使用异步驱动或异步策略，禁止在异步请求链中直接调用同步客户端。
* 避免在异步函数中调用阻塞操作，例如同步 HTTP/Redis 请求、`time.sleep()`、大文件同步读写。
* 如必须调用阻塞逻辑，应说明原因，并按项目现有方式封装或隔离。

## 日志与字符串输出

* 严禁使用 `print()`。
* 严禁在业务代码中直接 `import logging` 或使用原生 `logging`。
* 必须使用项目统一日志工具：`from app.core.log import log`。
* 仅允许使用：`log.info()`、`log.error()`、`log.warning()`、`log.debug()`。
* 日志、异常消息和其他字符串模板输出优先使用 f-string，尽量避免字符串拼接、`%` 格式化或 `.format()`。
* 日志不得输出密码、Token、密钥、身份证号、手机号等敏感信息。
* 例外：`app/core/log/*.py` 和 `config/logger_config.py` 允许使用原生 `logging`。

## 异常处理

* 业务异常必须使用 `app.exceptions` 中的项目自定义异常，例如 `BizException`、`ParamsException`、`NotFoundException` 等。
* 异常信息必须包含清晰、具体、可定位的错误原因。
* service 层不要随意抛出 FastAPI 的 `HTTPException`，除非现有项目模式明确如此。
* 不要吞掉异常；捕获异常时必须保留必要上下文并记录日志或转换为项目统一异常。
* 不要用异常控制正常业务流程。

## 类型、命名与注释

* 所有新增或修改的函数必须包含类型提示。
* 关键业务逻辑必须编写中文 docstring。
* 命名应表达业务含义，避免滥用 `data`、`result`、`tmp` 等泛化名称。
* Python 3.12 代码优先使用现代类型写法，例如 `list[str]`、`dict[str, Any]`。
* 使用 `collections.abc.Callable`，不要使用 `typing.Callable`。
* import 必须分组排序：标准库、第三方库、项目内部包。
* 文档、配置和源码统一保持 UTF-8 编码，修改中文内容时不得改变文件编码。

## Git Commit 规范

- 生成 git commit 提交信息时，优先使用中文描述变更内容。
- 如使用约定式提交格式，`feat`、`fix`、`refactor`、`docs`、`test`、`chore` 等类型前缀可以保留英文，但提交标题和正文说明应优先使用中文。

## Ruff 与 ty 规范

项目使用 Ruff 进行 Lint 与格式化，使用 ty 进行静态类型检查与语言服务器支持，配置均位于 `pyproject.toml`。

```bash
uv run ruff format .
uv run ruff check .
uv run ty check
```

硬性要求：
* 生成或修改的代码不得引入新的 Ruff 错误。
* 不要直接执行 `uv run ruff check . --fix`。
* 需要修复 Ruff 问题时，应人工判断并手动修改。
* 必须遵守 `T201`：禁止 `print()`。
* 必须遵守 `TID251`：业务代码禁止 `import logging`。
* 必须遵守 `I`：import 排序。
* 必须遵守 `UP`：使用 Python 3.12 推荐写法。
* `ty` 当前按 warning 方式接入，用于持续观察类型诊断；新增代码应尽量避免引入新的明显类型问题。
* 例外：`main.py` 允许非顶部导入，因为启动初始化顺序可能有意为之。

## 测试与验证

* 修改代码后至少运行 `uv run ruff format .`、`uv run ruff check .` 和 `uv run ty check`。
* 如果工作区存在无关改动，运行格式化前必须确认影响范围；必要时优先格式化本次修改的 Python 文件，并在最终回复中说明未执行整仓库格式化的原因。
* 如果只修改文档，可不运行 Ruff、ty 和测试，但最终回复中必须说明原因。
* 如果存在相关测试，优先运行最小相关测试集。
* 常见测试命令：`uv run pytest`。
* 修复 bug 时，优先补充或更新能复现问题的测试。
* 新增功能时，优先补充接口层、service 层或关键业务规则测试。
* 如果测试依赖数据库、Redis、外部服务或本地环境而无法运行，在最终回复中说明原因和风险。

## 数据库规范

* 遵循项目现有 SQLAlchemy 异步写法。
* 不要在没有必要的情况下使用原生 SQL。
* 必须使用原生 SQL 时，要使用参数绑定，避免 SQL 注入。
* 避免 N+1 查询，必要时使用合适的 join、selectinload 或项目既有优化方式。

## 禁止事项

* 不要提交或生成真实密钥、Token、密码、生产数据库地址。
* 不要修改真实环境文件（`.env`、`.env.*`）、生产配置或凭证文件，除非用户明确要求且内容不包含真实敏感值。
* 不要执行删除数据、清空目录、重置 Git 历史等破坏性操作，除非用户明确要求。
* 不要擅自格式化整个仓库之外的文件。
* 不要为了通过检查而删除有效业务逻辑。
* 不要引入与项目规范冲突的日志、异常、数据库或响应风格。

## 完成标准

* 变更是否只覆盖用户请求范围。
* 是否保持 FastAPI 与 SQLAlchemy 异步模式。
* 是否没有新增 `print()` 或业务代码 `logging`。
* 是否使用项目自定义异常表达业务错误。
* 函数是否包含类型提示。
* 关键业务逻辑是否有中文 docstring。
* import 是否正确分组排序。
* 是否运行 Ruff format/check 与 ty check。
* 是否运行相关测试，或说明无法运行的原因。
* 最终回复应包含修改摘要、验证命令、结果和剩余风险。

## 回复要求

* 使用中文回复用户。
* 先给结论，再说明关键改动和原因。
* 完成代码修改后，列出关键文件、关键改动和验证结果。
* 发现无关问题时，可在“额外建议”中说明，但不要擅自修改。
