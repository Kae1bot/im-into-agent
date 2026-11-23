"""适配器统一接口。每个 IM 实现 resolve() 和 read()。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..contract import QuerySpec, ReadResult, ResolveResult


class Adapter(ABC):
    """一个 IM 的读取适配器。"""

    #: 数据来源标识，写入 ReadResult.source
    source: str

    @abstractmethod
    def resolve(self, name: str, kind: str = "any") -> ResolveResult:
        """把自然语言名字解析为稳定 ID。"""

    @abstractmethod
    def read(self, query: QuerySpec) -> ReadResult:
        """按查询读消息，返回统一结果。"""
