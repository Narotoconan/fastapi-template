import os


def pytest_configure() -> None:
    """在测试模块收集前注入不具备生产用途的测试凭据。"""
    os.environ.setdefault("DB_PASSWORD", "test-database-password")
    os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-with-32-characters")
