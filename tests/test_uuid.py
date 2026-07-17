from uuid import UUID

from uuid6 import uuid7


def test_uuid7_returns_standard_uuid_v7() -> None:
    """uuid6 应生成标准库 UUID 类型的 UUIDv7。"""
    generated_uuid = uuid7()

    assert isinstance(generated_uuid, UUID)
    assert generated_uuid.version == 7
