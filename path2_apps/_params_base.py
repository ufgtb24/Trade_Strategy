"""path2_apps 各 pattern 共用的 Params 形式协议基类。

抽出「嵌套-section dataclass 的读写协议」——`default` / `from_yaml` / `to_dict` /
`from_dict`——这些方法在每个 app 里逐字相同、与具体走势无关(纯形式代码)。app 侧只留
**业务内容**:section 子 dataclass 定义(有哪些参数)+ 非平凡的 `*_kwargs` 映射
(参数→detector 签名)+ `load_params` / `DEFAULT_YAML_PATH`(依赖 app 自身路径)。

单一来源的收益:形式协议只有一份,不再随 app 复制粘贴而漂移——例如 `try_conplex_where`
曾因是主 app 旧拷贝、缺 `to_dict` 而在扫描时静默丢失 snapshot;继承本基类后天生具备,
该类 bug 从结构上不可能再发生。

基类成立的前提(刻意保持浅,不为假想情况预留):
- 子类是 `@dataclass(frozen=True)`,其**每个字段都是一个 section 子 dataclass**
  (值可由 `SectionClass(**dict)` 构造)。若将来出现非-section 的顶层标量字段,
  在子类覆写或扩展本基类,而非把钩子塞进这里。
- 因各 app 的 params.py 都 `from __future__ import annotations`(字段注解退化为字符串),
  section 类须用 `typing.get_type_hints` 解析,不能读 `dataclasses.Field.type`。
"""
from __future__ import annotations

import warnings
from dataclasses import asdict, fields
from typing import ClassVar, get_type_hints


class ParamsBase:
    """嵌套-section params 的形式协议(见模块 docstring)。子类须是 `@dataclass`。"""

    # 运行时字段白名单:to_dict 前从顶层 pop(预留 hook,默认空集)。
    RUNTIME_FIELDS: ClassVar[frozenset] = frozenset()

    @classmethod
    def _sections(cls) -> dict:
        """{section 字段名: section dataclass}——由 dataclass 字段 + 解析后注解派生。"""
        hints = get_type_hints(cls)
        return {f.name: hints[f.name] for f in fields(cls)}

    @classmethod
    def default(cls):
        """全默认实例(各 section 用其 dataclass field default)。"""
        return cls()

    def to_dict(self) -> dict:
        """全量参数 dict(嵌套 by section),供 scan snapshot / params_override 通道使用。"""
        d = asdict(self)
        for k in self.RUNTIME_FIELDS:
            d.pop(k, None)
        return d

    @classmethod
    def from_yaml(cls, path):
        """从 yaml 加载;顶层 + 每个 section 都校验未知 key(嵌套堵 yaml 拼错静默无效陷阱)。
        缺失 section / 缺失字段 → 用子 dataclass field default 兜底。"""
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError(f"({path}) 根必须是映射")
        sections = cls._sections()
        unknown_top = set(data) - set(sections)
        if unknown_top:
            raise ValueError(
                f"({path}) 含未知顶层 section: {sorted(unknown_top)} "
                f"(已知 section: {sorted(sections)})"
            )
        instances = {}
        for name, sect_cls in sections.items():
            sect_data = data.get(name) or {}
            if not isinstance(sect_data, dict):
                raise ValueError(f"({path}) section '{name}' 必须是映射")
            known = {f.name for f in fields(sect_cls)}
            unknown = set(sect_data) - known
            if unknown:
                raise ValueError(
                    f"({path}) section '{name}' 含未知字段: "
                    f"{sorted(unknown)} (可能拼错或字段已删;已知字段集见 {sect_cls.__name__})"
                )
            instances[name] = sect_cls(**sect_data)
        return cls(**instances)

    @classmethod
    def from_dict(cls, d: dict, strict: bool = False):
        """从 dict 重建。strict=True 未知 section/字段 raise(扫描入口用);
        strict=False 警告丢弃、缺失字段用 default(web 消费老 snapshot 用)。"""
        sections = cls._sections()
        unknown_top = set(d) - set(sections)
        if unknown_top:
            if strict:
                raise ValueError(f"params dict 含未知顶层 section: {sorted(unknown_top)}")
            warnings.warn(f"params dict 忽略未知 section: {sorted(unknown_top)}")
        instances = {}
        for name, sect_cls in sections.items():
            sect = dict(d.get(name) or {})
            known = {f.name for f in fields(sect_cls)}
            unknown = set(sect) - known
            if unknown:
                if strict:
                    raise ValueError(f"params dict section '{name}' 含未知字段: {sorted(unknown)}")
                warnings.warn(f"params dict section '{name}' 忽略未知字段: {sorted(unknown)}")
                for k in unknown:
                    sect.pop(k)
            instances[name] = sect_cls(**sect)
        return cls(**instances)
