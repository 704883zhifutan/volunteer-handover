"""能力边界：本项目"绝不能做"的事，在这里被写成代码而不是文档。

理由：能力边界写在提示词里，模型可以说服自己绕过去；写在类型和方法上，绕不过去。
对应访谈事实 f05（不自动指派医疗/安保、不替代现场指挥）、f52（不自动对外承诺）、
f32（只读导出，写回/外部消息/执行接口不开放）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple

# 硬清单：任何一项出现在配置或调用里，运行即失败。改这个清单需要书面审核同意。
FORBIDDEN_CAPABILITIES: Tuple[str, ...] = (
    "write_back",            # 写回业务系统
    "send_external_message", # 发外部消息 / 通知
    "auto_assign",           # 自动指派岗位（尤其医疗、安保）
    "auto_confirm",          # 自动确认，绕过人工
    "approve",               # 代替授权人员审批
    "overwrite_original",    # 覆盖原始记录
    "fill_missing_default",  # 为缺失值补默认值
    "retry_business_action", # 悄悄重试业务动作
)


class BoundaryViolation(RuntimeError):
    """越界调用。这是错误，不是警告。"""


@dataclass(frozen=True)
class Boundary:
    write_apis: Tuple[str, ...] = ()
    outbound_channel: str = "none"
    auto_assign_categories: Tuple[str, ...] = ()

    @classmethod
    def from_config(cls, cfg: dict) -> "Boundary":
        return cls(
            write_apis=tuple(cfg.get("write_apis") or ()),
            outbound_channel=str(cfg.get("outbound_channel") or "none"),
            auto_assign_categories=tuple(cfg.get("auto_assign_categories") or ()),
        )

    def violations(self) -> list:
        """返回配置中出现的越界项，供 C9 校验输出。"""
        found = []
        if self.write_apis:
            found.append(("write_apis", ", ".join(self.write_apis)))
        if self.outbound_channel not in ("none", "", None):
            found.append(("outbound_channel", self.outbound_channel))
        if self.auto_assign_categories:
            found.append(("auto_assign_categories", ", ".join(self.auto_assign_categories)))
        return found

    def guard(self, capability: str) -> None:
        if capability in FORBIDDEN_CAPABILITIES:
            raise BoundaryViolation(
                f"能力 {capability!r} 属于禁用清单；本项目只做读取、校验与建议。"
            )


def assert_capabilities_allowed(capabilities: Iterable[str]) -> None:
    for cap in capabilities:
        if cap in FORBIDDEN_CAPABILITIES:
            raise BoundaryViolation(f"禁用能力被请求：{cap!r}")
