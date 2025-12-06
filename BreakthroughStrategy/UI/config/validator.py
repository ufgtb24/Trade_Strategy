"""参数验证器

复用 UIParamLoader 的验证逻辑，并提供额外的验证功能
"""

from typing import Any, Tuple, List


class InputValidator:
    """参数输入验证器"""

    @staticmethod
    def validate_int(value: str, min_val: int, max_val: int) -> Tuple[bool, int, str]:
        """
        验证整数参数

        Args:
            value: 待验证的字符串值
            min_val: 最小值
            max_val: 最大值

        Returns:
            (是否合法, 钳制后的值, 错误信息)
        """
        try:
            val = int(value)
            if val < min_val:
                return False, min_val, f"Value must be >= {min_val}"
            if val > max_val:
                return False, max_val, f"Value must be <= {max_val}"
            return True, val, ""
        except (TypeError, ValueError):
            return False, min_val, "Invalid integer format"

    @staticmethod
    def validate_float(
        value: str, min_val: float, max_val: float
    ) -> Tuple[bool, float, str]:
        """
        验证浮点数参数

        Args:
            value: 待验证的字符串值
            min_val: 最小值
            max_val: 最大值

        Returns:
            (是否合法, 钳制后的值, 错误信息)
        """
        try:
            val = float(value)
            if val < min_val:
                return False, min_val, f"Value must be >= {min_val}"
            if val > max_val:
                return False, max_val, f"Value must be <= {max_val}"
            return True, val, ""
        except (TypeError, ValueError):
            return False, min_val, "Invalid float format"

    @staticmethod
    def validate_bool(value: Any) -> Tuple[bool, bool, str]:
        """
        验证布尔参数

        Args:
            value: 待验证的值

        Returns:
            (是否合法, 布尔值, 错误信息)
        """
        try:
            if isinstance(value, bool):
                return True, value, ""
            if isinstance(value, str):
                value_lower = value.lower()
                if value_lower in ("true", "1", "yes"):
                    return True, True, ""
                if value_lower in ("false", "0", "no"):
                    return True, False, ""
            return False, False, "Invalid boolean format"
        except Exception:
            return False, False, "Invalid boolean format"

    @staticmethod
    def validate_list(
        value: str, element_type: type = int
    ) -> Tuple[bool, List, str]:
        """
        验证列表参数（逗号分隔）

        Args:
            value: 待验证的字符串值，如 "5, 10, 20, 60"
            element_type: 元素类型（int或float）

        Returns:
            (是否合法, 解析后的列表, 错误信息)
        """
        try:
            if not value or not value.strip():
                return False, [], "List cannot be empty"

            # 分割并去除空格
            parts = [p.strip() for p in value.split(",")]

            # 转换类型
            result = []
            for part in parts:
                if element_type == int:
                    result.append(int(part))
                elif element_type == float:
                    result.append(float(part))
                else:
                    return False, [], f"Unsupported element type: {element_type}"

            return True, result, ""

        except ValueError as e:
            return False, [], f"Invalid {element_type.__name__} in list: {str(e)}"
        except Exception as e:
            return False, [], f"Invalid list format: {str(e)}"

    @staticmethod
    def validate_str(value: str) -> Tuple[bool, str, str]:
        """
        验证字符串参数

        Args:
            value: 待验证的字符串值

        Returns:
            (是否合法, 字符串值, 错误信息)
        """
        if value is None:
            return False, "", "String cannot be None"
        return True, str(value), ""


class WeightGroupValidator:
    """权重组参数验证器"""

    @staticmethod
    def validate_sum(
        weights: dict, tolerance: float = 0.001
    ) -> Tuple[bool, float, str]:
        """
        验证权重组的总和是否为1.0

        Args:
            weights: 权重字典，如 {'volume': 0.25, 'candle': 0.20, ...}
            tolerance: 容差，默认0.001

        Returns:
            (是否合法, 当前总和, 错误信息)
        """
        try:
            # 计算总和
            total = sum(float(v) for v in weights.values() if v is not None)

            # 检查是否接近1.0
            if abs(total - 1.0) <= tolerance:
                return True, total, ""
            else:
                return (
                    False,
                    total,
                    f"Sum of weights must be 1.0 (current: {total:.4f})",
                )

        except (TypeError, ValueError) as e:
            return False, 0.0, f"Invalid weight values: {str(e)}"

    @staticmethod
    def calculate_sum(weights: dict) -> float:
        """
        计算权重组的总和（用于实时显示）

        Args:
            weights: 权重字典

        Returns:
            总和
        """
        try:
            return sum(float(v) for v in weights.values() if v is not None)
        except (TypeError, ValueError):
            return 0.0
