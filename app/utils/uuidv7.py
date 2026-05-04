import datetime
import secrets
import time
import uuid
from typing import Union


class UUIDv7:
    """UUID v7生成器类

    UUID v7格式:
    - 前48位为UNIX时间戳(毫秒级)
    - 中间12位为版本和变体标识以及序列计数器
    - 最后62位为随机数据
    """

    # 类变量用于支持单调递增
    _last_timestamp: int = 0
    _counter: int = 0
    _counter_mask: int = 0x0FFF  # 12位计数器掩码
    _mutex_lock = None  # 在多线程环境下可以使用锁

    @classmethod
    def generate(cls, timestamp_ms: int | None = None) -> uuid.UUID:
        """
        生成一个UUID v7对象。

        Args:
            timestamp_ms: 可选的毫秒级时间戳，如果不提供则使用当前时间

        Returns:
            uuid.UUID: 生成的UUID v7对象

        Note:
            该方法在多线程环境下不是线程安全的。在多线程应用中，
            请考虑使用threading.Lock保护这个方法的调用。
        """
        try:
            # 如果有定义锁并且锁可用，则获取锁（多线程环境）
            if cls._mutex_lock:
                cls._mutex_lock.acquire()

            # 获取或使用提供的毫秒级时间戳
            current_ms = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)

            # 验证时间戳合法性
            if current_ms < 0:
                raise ValueError("时间戳必须是非负数")

            # 支持单调递增
            if current_ms <= cls._last_timestamp:
                # 如果时间戳相同或倒退，增加计数器
                cls._counter = (cls._counter + 1) & cls._counter_mask
                # 如果计数器溢出，只能等待时间戳前进
                if cls._counter == 0:
                    # 等待下一毫秒
                    while current_ms <= cls._last_timestamp:
                        current_ms = int(time.time() * 1000)
            else:
                # 新的时间戳，重置计数器
                cls._counter = 0

            # 更新最后时间戳
            cls._last_timestamp = current_ms

            # 生成UUID字节
            return cls._create_uuid_bytes(current_ms, cls._counter)
        finally:
            # 释放锁（如果有的话）
            if cls._mutex_lock:
                cls._mutex_lock.release()

    @staticmethod
    def _create_uuid_bytes(timestamp_ms: int, counter: int) -> uuid.UUID:
        """
        根据时间戳和计数器创建UUID字节。

        根据UUID v7规范:
        - 前48位为UNIX时间戳(毫秒级)
        - 接下来4位为版本号(7)
        - 接下来12位为序列计数器
        - 接下来2位为变体(RFC4122)
        - 剩余62位为随机数据

        Args:
            timestamp_ms: 毫秒级时间戳
            counter: 序列计数器值

        Returns:
            uuid.UUID: 生成的UUID对象

        Raises:
            ValueError: 如果时间戳超出48位表示范围
        """
        # 检查时间戳范围
        if timestamp_ms >= (1 << 48):
            raise ValueError(f"时间戳超出48位表示范围: {timestamp_ms}")

        # 准备16字节的缓冲区
        uuid_bytes = bytearray(16)

        # 时间戳转为字节 (48位 = 6字节)
        timestamp_bytes = timestamp_ms.to_bytes(6, byteorder="big")
        uuid_bytes[0:6] = timestamp_bytes

        # 版本(4位)和计数器高4位 (总共8位 = 1字节)
        # 设置版本为7 (0111)
        uuid_bytes[6] = ((counter >> 8) & 0x0F) | 0x70

        # 计数器低8位 (8位 = 1字节)
        uuid_bytes[7] = counter & 0xFF

        # 变体(2位)和随机数据高6位 (总共8位 = 1字节)
        # 设置变体为RFC4122 (10xx)
        rand_byte = secrets.randbits(8)
        uuid_bytes[8] = (rand_byte & 0x3F) | 0x80

        # 剩余随机字节 (7字节)
        rand_bytes = secrets.token_bytes(7)
        uuid_bytes[9:16] = rand_bytes

        return uuid.UUID(bytes=bytes(uuid_bytes))

    @classmethod
    def generate_str(cls, timestamp_ms: int | None = None) -> str:
        """
        生成UUID v7并返回其字符串表示。

        Args:
            timestamp_ms: 可选的毫秒级时间戳

        Returns:
            str: UUID v7的字符串表示
        """
        return str(cls.generate(timestamp_ms))

    @staticmethod
    def from_datetime(dt: datetime.datetime) -> uuid.UUID:
        """
        从datetime对象生成UUID v7。

        Args:
            dt: datetime对象

        Returns:
            uuid.UUID: 生成的UUID v7对象
        """
        timestamp_ms = int(dt.timestamp() * 1000)
        return UUIDv7.generate(timestamp_ms)

    @staticmethod
    def get_timestamp(uuid_v7: Union[uuid.UUID, str]) -> datetime.datetime:
        """
        从UUID v7中提取时间戳。

        Args:
            uuid_v7: UUID v7对象或其字符串表示

        Returns:
            datetime.datetime: 提取的时间戳对应的datetime对象

        Raises:
            ValueError: 如果提供的UUID不是v7版本
            ValueError: 如果提供的UUID字符串格式不正确
            TypeError: 如果提供的参数类型不正确
        """
        if isinstance(uuid_v7, str):
            try:
                uuid_obj = uuid.UUID(uuid_v7)
            except ValueError as e:
                raise ValueError(f"提供的UUID字符串格式不正确: {e}") from None
        elif isinstance(uuid_v7, uuid.UUID):
            uuid_obj = uuid_v7
        else:
            raise TypeError(f"参数类型必须是uuid.UUID或字符串，而不是{type(uuid_v7)}")

        # 检查版本是否为7
        if uuid_obj.version != 7:
            raise ValueError(f"提供的UUID不是v7版本: {uuid_obj}")

        # 提取时间戳字节（前6字节）
        timestamp_bytes = uuid_obj.bytes[:6]
        timestamp_ms = int.from_bytes(timestamp_bytes, byteorder="big")

        # 转换为datetime对象
        try:
            return datetime.datetime.fromtimestamp(timestamp_ms / 1000.0)
        except (ValueError, OverflowError) as e:
            raise ValueError(f"无效的时间戳值: {timestamp_ms}, 错误: {e}") from None

    # 添加多线程支持的方法
    @staticmethod
    def enable_thread_safety():
        """
        启用线程安全模式。
        这将使用threading.Lock保护UUID生成过程。

        Note:
            必须在调用生成方法前调用此方法。
            该方法需要threading模块支持。
        """
        import threading

        UUIDv7._mutex_lock = threading.Lock()


__all__ = ["UUIDv7"]
