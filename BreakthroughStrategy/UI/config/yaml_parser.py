"""YAML 注释解析器

从 YAML 文件中提取参数的中文注释
"""

from pathlib import Path
from typing import Dict, Optional
import re


class YamlCommentParser:
    """YAML 注释解析器"""

    def __init__(self, yaml_path: Path):
        """
        初始化解析器

        Args:
            yaml_path: YAML 文件路径
        """
        self.yaml_path = yaml_path
        self.comments = {}
        self._parse_comments()

    def _parse_comments(self):
        """
        解析 YAML 文件中的注释

        注释格式:
        1. 行尾注释: key: value  # 注释
        2. 行首注释: # 注释
                     key: value
        """
        if not self.yaml_path.exists():
            return

        with open(self.yaml_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        current_section = None
        current_subsection = None
        prev_comment = None

        for line in lines:
            stripped = line.strip()

            # 跳过空行
            if not stripped:
                prev_comment = None
                continue

            # 纯注释行
            if stripped.startswith("#"):
                comment_text = stripped.lstrip("#").strip()
                # 保存注释,等待关联到下一个参数
                prev_comment = comment_text
                continue

            # 解析参数行
            # 匹配格式: key: value  # 注释
            match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):(.*)$", stripped)
            if not match:
                prev_comment = None
                continue

            key = match.group(1)
            rest = match.group(2).strip()

            # 检查是否有行尾注释
            inline_comment = None
            if "#" in rest:
                parts = rest.split("#", 1)
                inline_comment = parts[1].strip()

            # 判断是否是分组（value 为空或只有注释）
            is_section = not rest or rest.startswith("#")

            if is_section:
                # 这是一个分组
                if current_section is None:
                    # 顶级分组
                    current_section = key
                    current_subsection = None
                else:
                    # 子分组
                    current_subsection = key
            else:
                # 这是一个参数
                # 确定完整的参数路径
                if current_subsection:
                    # 三级参数: section.subsection.key
                    param_path = f"{current_section}.{current_subsection}.{key}"
                elif current_section:
                    # 二级参数: section.key
                    param_path = f"{current_section}.{key}"
                else:
                    # 顶级参数
                    param_path = key

                # 优先使用行尾注释,否则使用前一行的注释
                comment = inline_comment or prev_comment
                if comment:
                    self.comments[param_path] = comment

                prev_comment = None

    def get_comment(self, param_path: str) -> Optional[str]:
        """
        获取参数的注释

        Args:
            param_path: 参数路径，如 'peak_weights.volume' 或 'breakthrough_detector.window'

        Returns:
            注释文本，如果没有注释则返回 None
        """
        return self.comments.get(param_path)

    def get_all_comments(self) -> Dict[str, str]:
        """
        获取所有注释

        Returns:
            参数路径到注释的映射
        """
        return self.comments.copy()
