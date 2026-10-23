"""极简 YAML 子集解析器（无第三方依赖）。

支持：注释、嵌套映射（空格缩进）、标量列表、`[]`/`{}` 空集合、
null/true/false/int/float/带引号字符串。

不支持：锚点、多文档、行内非空集合、Tab 缩进、跨行字符串。
遇到不支持的写法会抛 ConfigError 并给出位置，不静默降级。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple


class ConfigError(ValueError):
    """配置格式错误。带上行号，方便直接定位到文件。"""


def _strip_comment(line: str) -> str:
    """去掉行内注释，引号内的 # 不算注释。"""
    out = []
    quote = ""
    prev = ""
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = ""
            prev = ch
            continue
        if ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#" and (prev == "" or prev in " \t"):
            break
        else:
            out.append(ch)
        prev = ch
    return "".join(out).rstrip()


def _scalar(token: str) -> Any:
    t = token.strip()
    if t == "" or t in ("null", "~", "None"):
        return None
    if t == "[]":
        return []
    if t == "{}":
        return {}
    low = t.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        return t[1:-1]
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        pass
    return t


def _tokenize(text: str) -> List[Tuple[int, int, str]]:
    tokens: List[Tuple[int, int, str]] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = _strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        body = line.strip()
        if body.startswith("\t") or "\t" in line[: indent + 1]:
            raise ConfigError(f"第 {line_no} 行：不支持 Tab 缩进")
        tokens.append((indent, line_no, body))
    return tokens


def _parse_block(tokens, index, indent):
    if tokens[index][2].startswith("- "):
        return _parse_list(tokens, index, indent)
    return _parse_map(tokens, index, indent)


def _parse_map(tokens, index, indent):
    out: Dict[str, Any] = {}
    i = index
    while i < len(tokens):
        ind, line_no, body = tokens[i]
        if ind < indent:
            break
        if ind > indent:
            raise ConfigError(f"第 {line_no} 行：缩进比同级多，但没有上级键")
        if ":" not in body:
            raise ConfigError(f"第 {line_no} 行：缺少 ':'，应该是 key: value")
        key, _, rest = body.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest:
            out[key] = _scalar(rest)
            i += 1
            continue
        if i + 1 < len(tokens) and tokens[i + 1][0] > indent:
            child, i = _parse_block(tokens, i + 1, tokens[i + 1][0])
            out[key] = child
        else:
            out[key] = None
            i += 1
    return out, i


def _parse_list(tokens, index, indent):
    items: List[Any] = []
    i = index
    while i < len(tokens):
        ind, line_no, body = tokens[i]
        if ind < indent:
            break
        if ind != indent or not body.startswith("- "):
            raise ConfigError(f"第 {line_no} 行：列表项必须同缩进且以 '- ' 开头")
        entry = body[2:].strip()
        i += 1
        if ":" in entry and entry[0] not in "\"'":
            key, _, rest = entry.partition(":")
            item: Dict[str, Any] = {key.strip(): _scalar(rest)}
            while i < len(tokens) and tokens[i][0] > indent:
                k, _, r = tokens[i][2].partition(":")
                item[k.strip()] = _scalar(r)
                i += 1
            items.append(item)
        else:
            items.append(_scalar(entry))
    return items, i


def parse(text: str) -> Dict[str, Any]:
    tokens = _tokenize(text)
    if not tokens:
        return {}
    result, consumed = _parse_block(tokens, 0, tokens[0][0])
    if consumed != len(tokens):
        line_no = tokens[consumed][1]
        raise ConfigError(f"第 {line_no} 行：无法解析到文件末尾，检查缩进是否一致")
    if not isinstance(result, dict):
        raise ConfigError("顶层必须是映射（key: value）")
    return result


def load(path) -> Dict[str, Any]:
    return parse(Path(path).read_text(encoding="utf-8"))


def get(config: Dict[str, Any], dotted: str, default: Any = None) -> Any:
    """按 'pilot.batch_id' 取值；缺失返回默认值，不抛异常。"""
    node: Any = config
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node
