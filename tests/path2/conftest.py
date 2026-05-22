import pytest
from path2 import config


@pytest.fixture(autouse=True)
def _reset_runtime_checks():
    """每个测试后还原 RUNTIME_CHECKS,避免 set_runtime_checks 跨测试泄漏。"""
    saved = config.RUNTIME_CHECKS
    yield
    config.RUNTIME_CHECKS = saved
