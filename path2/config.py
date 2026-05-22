import os


def _env_off(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("0", "false", "off", "no")


RUNTIME_CHECKS: bool = not _env_off("PATH2_RUNTIME_CHECKS")


def set_runtime_checks(enabled: bool) -> None:
    """运行时全局切换(测试 / 生产热关)。"""
    global RUNTIME_CHECKS
    RUNTIME_CHECKS = enabled
