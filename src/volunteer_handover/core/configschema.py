"""配置白名单：拼错一个键，不许静默失效。

为什么需要这个模块：这个项目里**关掉一条校验**和**拼错一个键**在结果上长得一模一样——
比如把 `require_confirm_status` 打成 `require_confirm_staus`，代码读不到就是 `None`，
于是"版本未确认"这一整类异常悄悄消失，而清单看起来只是"干净了一些"。

这是 F9（假状态）的一种：不是数据造假，是配置造假。所以未知键直接让运行 blocked，
并把最像的那个键名指出来——拼错的人一眼能改，而不是去猜为什么少了一类异常。
"""

from __future__ import annotations

import difflib
from typing import Any, Dict, List

from .fields import SCOPE_ANOMALY_TYPES
from .times import parse_ts

# 允许出现的配置路径（顶层段 → 叶子键）。新增配置必须同时改这里和 config/default.yaml。
KNOWN: Dict[str, tuple] = {
    "project": ("name", "version", "mode"),
    "pilot": ("batch_id", "desk_dry_run", "page_item_limit", "max_review_hours"),
    "scope": ("excluded_position_categories", "allowed_anomaly_types"),
    "time": ("as_of", "backfill_threshold_minutes"),
    "versions": ("require_validity_window", "require_confirm_status"),
    "boundary": ("write_apis", "outbound_channel", "auto_assign_categories"),
    "output": ("dir", "max_page_items"),
}

_INT = {"pilot.page_item_limit", "pilot.max_review_hours", "output.max_page_items"}
_FLOAT_NULLABLE = {"time.backfill_threshold_minutes"}
_BOOL = {
    "pilot.desk_dry_run",
    "versions.require_validity_window",
    "versions.require_confirm_status",
}
_LIST = {
    "scope.excluded_position_categories",
    "scope.allowed_anomaly_types",
    "boundary.write_apis",
    "boundary.auto_assign_categories",
}
_STR = {
    "project.name",
    "project.version",
    "project.mode",
    "pilot.batch_id",
    "time.as_of",
    "boundary.outbound_channel",
    "output.dir",
}


def _flat(config: Dict[str, Any]) -> Dict[str, Any]:
    """只展开两层（本项目的配置就是两层的）。更深的结构视为类型错误。"""
    flat: Dict[str, Any] = {}
    for section, body in (config or {}).items():
        if isinstance(body, dict):
            for key, value in body.items():
                flat[f"{section}.{key}"] = value
        else:
            flat[str(section)] = body  # 顶层直接是标量：当作未知项报出来
    return flat


def _suggest(path: str, candidates) -> str:
    pool = [f"{section}.{key}" for section in KNOWN for key in KNOWN[section]]
    pool += list(KNOWN)
    close = difflib.get_close_matches(path, pool, n=1, cutoff=0.72)
    return f"（是不是 {close[0]}？）" if close else ""


def validate(config: Dict[str, Any]) -> List[str]:
    """返回人话问题列表；空列表表示配置可信。"""
    problems: List[str] = []
    if not isinstance(config, dict):
        return [f"配置不是一个映射，而是 {type(config).__name__}"]

    for section, body in config.items():
        if section not in KNOWN:
            problems.append(f"未知配置段 `{section}`{_suggest(str(section), KNOWN)}")
            continue
        if not isinstance(body, dict):
            problems.append(f"配置段 `{section}` 应该是一组键值，实际是 {type(body).__name__}")
            continue
        for key in body:
            if key not in KNOWN[section]:
                problems.append(
                    f"未知配置项 `{section}.{key}`（{section} 段只认 {'、'.join(KNOWN[section])}）"
                    f"{_suggest(f'{section}.{key}', KNOWN[section])}"
                )

    flat = _flat(config)
    for path, value in flat.items():
        if "." not in path:
            continue  # 顶层标量已经按"未知配置段"报过了
        if path in _INT:
            if isinstance(value, bool) or not isinstance(value, int):
                problems.append(f"`{path}` 应该是整数，实际是 {value!r}")
            elif value <= 0:
                problems.append(f"`{path}` 应该大于 0，实际是 {value}")
        elif path in _FLOAT_NULLABLE:
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                problems.append(f"`{path}` 应该是数字或 null，实际是 {value!r}")
        elif path in _BOOL:
            if not isinstance(value, bool):
                problems.append(f"`{path}` 应该是 true/false，实际是 {value!r}")
        elif path in _LIST:
            if not isinstance(value, list):
                problems.append(f"`{path}` 应该是列表，实际是 {type(value).__name__}")
        elif path in _STR:
            if not isinstance(value, str):
                problems.append(f"`{path}` 应该是字符串，实际是 {value!r}")

    as_of = flat.get("time.as_of")
    if isinstance(as_of, str) and as_of.strip() and parse_ts(as_of) is None:
        problems.append(f"`time.as_of` 无法解析成时间：{as_of!r}（示例 2026-10-03T16:00:00）")

    allowed = flat.get("scope.allowed_anomaly_types")
    if isinstance(allowed, list):
        unknown = [t for t in allowed if t not in SCOPE_ANOMALY_TYPES]
        if unknown:
            problems.append(
                "`scope.allowed_anomaly_types` 里出现未知异常类型："
                + "、".join(map(str, unknown))
                + "（可用：" + "、".join(SCOPE_ANOMALY_TYPES) + "）"
            )

    mode = flat.get("project.mode")
    if isinstance(mode, str) and mode != "readonly":
        problems.append(f"`project.mode` 只能是 readonly，实际是 {mode!r}（本项目没有写入模式）")

    return problems


def describe(problems: List[str]) -> str:
    return "配置不成立，本次不出结论：" + "；".join(problems)
