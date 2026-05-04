# 统一响应格式使用指南

## 快速上手

```python
from app.schemas.response import ResponseSchema, PageResponseSchema, PageParams
```

---

## 一、普通成功响应

```python
from app.schemas.response import ResponseSchema

# 返回数据
return ResponseSchema.ok(data={"id": 1, "name": "张三"})

# 自定义消息
return ResponseSchema.ok(data=user_dict, message="获取成功")

# 无数据时
return ResponseSchema.ok(message="操作成功")
```

响应体：
```json
{"code": 0, "message": "获取成功", "result": {"id": 1, "name": "张三"}}
```

---

## 二、分页响应

### 接口接收分页参数

```python
from fastapi import Query

async def get_list(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
):
    ...
```

> 也可以用 `PageParams` 作为 Body 接收分页参数：
> ```python
> from app.schemas.response import PageParams
> async def get_list(params: PageParams): ...
> # params.page / params.page_size / params.offset / params.limit
> ```

### 返回分页数据

```python
from app.schemas.response import PageResponseSchema

items = [{"id": 1, "name": "张三"}, {"id": 2, "name": "李四"}]
total = 56  # 总记录数（从数据库 COUNT 查询获得）

return PageResponseSchema.ok(
    items=items,
    total=total,
    page=page,
    page_size=page_size,
)
```

响应体：
```json
{
  "code": 0,
  "message": "success",
  "result": {
    "items": [{"id": 1, "name": "张三"}, {"id": 2, "name": "李四"}],
    "pagination": {
      "page": 1,
      "page_size": 10,
      "total": 56,
      "total_pages": 6,
      "has_next": true,
      "has_prev": false
    }
  }
}
```

---

## 三、文件 / 二进制下载

> ⚠️ 文件下载**不使用** JSON 响应格式，直接返回 `StreamingResponse` 或 `FileResponse`。

```python
from fastapi.responses import StreamingResponse, FileResponse
import io

# 场景一：内存中动态生成（CSV、Excel 等）
async def export_csv():
    content = "id,name\n1,张三\n2,李四".encode("utf-8-sig")  # BOM 兼容 Excel
    return StreamingResponse(
        io.BytesIO(content),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=export.csv"},
    )

# 场景二：返回磁盘上已有的文件
async def download_file():
    return FileResponse(
        path="/data/files/report.pdf",
        media_type="application/pdf",
        filename="report.pdf",
    )
```

---

## 四、响应结构总览

```
普通响应:
{
  "code":    0,           # 0=成功，非0=失败
  "message": "success",   # 描述信息
  "result":  {}           # 业务数据
}

分页响应:
{
  "code": 0,
  "message": "success",
  "result": {
    "items": [...],       # 当前页数据列表
    "pagination": {
      "page":        1,   # 当前页码
      "page_size":  10,   # 每页条数
      "total":      56,   # 总记录数
      "total_pages": 6,   # 总页数
      "has_next":  true,  # 是否有下一页
      "has_prev": false   # 是否有上一页
    }
  }
}
```

---

## 五、错误响应（由全局异常处理器自动生成）

业务层只需**抛出异常**，无需手动构建错误响应，详见 `app/exceptions/README.md`。

```python
from app.exceptions import NotFoundException, BizException, ErrorCode

raise NotFoundException(message="订单不存在")
# → {"code": 3001, "message": "订单不存在", "result": {}}

raise BizException(ErrorCode.FAIL, message="库存不足")
# → {"code": -1, "message": "库存不足", "result": {}}
```

