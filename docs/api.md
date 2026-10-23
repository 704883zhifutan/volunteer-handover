# 数据契约与接口

两件事说清楚：**输入长什么样**（4 个 CSV 的列约定），**输出与调用长什么样**（CLI 退出码、
产物文件、模块函数）。

约定：所有输入只读；任何缺列都按"缺失"处理，不按空字符串兜底；时间一律 `YYYY-MM-DDTHH:MM:SS`。

---

## 1. 输入：四个 CSV

### `positions.csv` — 岗位字典

| 列 | 类型 | 说明 |
|---|---|---|
| `position_id` | str | 岗位代号，如 `P05` |
| `position_name` | str | 岗位名 |
| `category` | str | 类别；`医疗` / `安保` 会被 `scope.excluded_position_categories` 排除出试点 |
| `required_skill` | str | 必需技能标签，用于和 `shifts.skill_tags` 比对 |
| `site_id` | str | 岗位默认点位；与签到点位不一致会成 C1 缺项 |

### `shifts.csv` — 排班（16 列，**计划类记录**）

| 列 | 类型 | 说明 |
|---|---|---|
| `shift_id` | str | 班次编号，C7 检查唯一性 |
| `batch_id` | str | 批次；必须与 `pilot.batch_id` 一致，否则提示混批次 |
| `position_id` | str | 岗位；参与范围外判断 |
| `person_code` | str | 人员代号（脱敏），C2 重复占位的主键 |
| `skill_tags` | str | 以 `;` 分隔的技能标签 |
| `window_start` / `window_end` | ts | 班次时间窗；用于重叠、单位差异、与签到比对 |
| `window_minutes` | int | 声明时长；与实算不一致报"单位差异"（常见：小时填进分钟） |
| `confirm_status` | str | `confirmed` / `unconfirmed` / 空（缺失）—— 三值逻辑的入口 |
| `version_no` | str | 如 `v3` |
| `version_valid_from` / `version_valid_to` | ts | 有效期；`require_validity_window: true` 时越界报过期 |
| `superseded_by` | str | 被哪一版替代；非空且不同于自身即断链 |
| `void_reason` | str | 作废原因；作废必须写原因，不许删行 |
| `occurred_at` | ts | 业务发生时间（计划录入那一刻） |
| `received_at` | ts | 系统接收时间 |

> **计划类特殊性**：`occurred_at` 早于 `window_start` 是正常的（表格本来就先排）。
> 所以 C3 对它不判"时间倒挂"，只在 `received_at` 晚于班次开始时标记**疑似回填**。
> 这条规则在 `core/checks.py` 的 `PLANNED_FILES` 里，不要改成"统一判倒挂"——第一版就是
> 这么做的，跑出 10 条全误报。

### `checkins.csv` — 签到（**事件类记录**）

| 列 | 类型 | 说明 |
|---|---|---|
| `checkin_id` | str | 签到编号 |
| `shift_id` | str | 引用排班；找不到即"编号断链"（C7） |
| `person_code` | str | 实际签到人；与排班不同即"排班表与现场不一致" |
| `site_id` | str | 实际点位；与岗位要求点位不同即缺项 |
| `checked_at` | ts | 签到时刻（设备时间） |
| `occurred_at` | ts | 业务发生时间 |
| `received_at` | ts | 系统接收时间；**事件类要求 ≥ occurred_at** |
| `source_tool` | str | 来源工具；含"文件库/批量/补录/群消息"时视为批量回填来源 |

### `handover.csv` — 交接（**事件类记录**）

| 列 | 类型 | 说明 |
|---|---|---|
| `handover_id` | str | 交接编号 |
| `shift_id` | str | 引用排班 |
| `from_person` / `to_person` | str | 交出人 / 接收人；相同即异常 |
| `handover_at` / `accepted_at` | ts | 交接时刻 / 签收时刻；后者空即"未签收" |
| `version_no` | str | 交接依据的版本；与排班当前版本不同即版本异常 |
| `open_items` | str | 未结项，格式见下 |
| `notes` | str | 备注 |

**`open_items` 格式**（分隔符用 `;` 和 `|`，**不能用 `:`**，会被 ISO 时间戳切碎）：

```
OI-1;补充冰块至 14:00;2026-10-03T14:00:00;Z0003;未结|OI-2;把对讲机交给下一班;2026-10-03T15:00:00;;未结
```

字段依次为 编号、事项、截止时间、责任人、状态。不足 5 段时**保留原始串并标记
"格式无法判定"**，不丢弃、不猜。责任人空的未结项会报"未结项归属缺失"。

---

## 2. 输出

`write_outputs(result, out_dir)` 只写 `out/`，共 5 个文件：

| 文件 | 内容 | 谁看 |
|---|---|---|
| `items.md` | 一页缺项清单（Markdown） | 现场协调员 |
| `items.csv` | 同上，12 列，含双时间与 locator | 流程协调员 |
| `handover.md` | 交接责任清单 + 未结项 | 流程协调员 |
| `snapshots.csv` | 每个输入文件的 sha256、行数、读取状态 | 质量负责人 |
| `audit.csv` | 谁在什么时候读/导出/确认了什么 | 质量负责人 |

`items.csv` 列顺序：

```
序号, 校验, 类型, 对象, 事实, 业务发生, 系统接收, 版本, 来源位置, 建议, 复核状态, 复核人
```

`来源位置` 形如 `shifts.csv#L5 + checkins.csv#L4`——`文件名#L物理行号`（首数据行为 `L2`）。
**每一条缺项都必须能靠这个坐标一跳回到原始行**，这是"可追溯"的验收方式。

---

## 3. 模块接口

```python
from volunteer_handover.core.engine import run, write_outputs
from volunteer_handover.core import boundary, checks, fields, handover, ids, items, loader, times, trace
from volunteer_handover.utils import config, csvio, logutil
```

| 函数 / 类 | 签名 | 说明 |
|---|---|---|
| `run` | `run(data_dir, config) -> RunResult` | 编排：加载 → 快照 → C1–C9 → 汇总。不写文件 |
| `write_outputs` | `write_outputs(result, out_dir) -> list[Path]` | 只写 out/ |
| `RunResult` | `.items` `.checks` `.dataset` `.warnings` `.excluded_shifts` `.blocked` `.summary()` | `blocked` 为真表示能力越界，CLI 退出 2 |
| `loader.load_dataset` | `load_dataset(data_dir, files=DEFAULT_FILES) -> Dataset` | 读失败不抛异常，记 `missing` + unavailable 快照 |
| `checks.all_checks` | `all_checks(dataset, positions_index, in_scope, boundary, config, checks) -> list[Finding]` | 九条校验统一入口 |
| `items.ItemSheet` | `ItemSheet(batch_id, findings, page_limit=40, ...)` | `.filtered()` `.page_warning()` `.render_markdown()` `.to_csv()` |
| `handover.build_checklist` | `build_checklist(handover_rows, shift_index, as_of) -> list[HandoverCheck]` | **只输出信号，不输出 `is_complete`**（G3 未确认） |
| `boundary.Boundary` | `Boundary.from_config(cfg)`；`.violations()`；`.guard(cap)` | 配置非空即越界，直接抛 `BoundaryViolation` |
| `fields.tri` | `tri(value) -> Tri` | `PRESENT` / `MISSING` / `UNCONFIRMED` |
| `times.dual_time_state` | `dual_time_state(occurred, received, threshold_minutes=None, source_tool="") -> str` | 阈值 `None` 时不判超时，只标批量回填 |
| `ids.build_shift_id` | `build_shift_id(batch, position, window_start, person) -> str` | **候选规则**，最终以业务方拍板为准（H5） |
| `trace.take_snapshot` | `take_snapshot(path, row_count) -> Snapshot` | 失败返回 `status="unavailable"`，不重试、不补值 |
| `config.load` | `load(path) -> dict`；`get(cfg, "a.b", default)` | 自写 YAML 子集解析；不支持写法抛带行号 `ConfigError` |

---

## 4. CLI

```bash
PYTHONPATH=src python3 -m volunteer_handover.main [选项]

  --data DIR              输入目录（默认 data/）
  --config FILE           配置文件（默认 config/default.yaml）
  --out DIR               输出目录（默认 out/）
  --max-print N           终端最多打印多少行（默认 40）
  --json                  输出机器可读摘要
  --simulate-failure FILE 故意让某个输入不可读，用于验收 C8（可重复）
  --version               版本号
```

**退出码**

| 码 | 含义 |
|---|---|
| `0` | 正常完成（含"有缺项"——有缺项是正常工作结果） |
| `2` | 边界越界（`blocked`）：配置里出现写回接口、外发通道或自动指派 |

**不会有的退出码**：没有"自动修复成功"这种码，因为工具没有修复能力。

```bash
# 演示读取失败如何被标记而不是被补值
PYTHONPATH=src python3 -m volunteer_handover.main --simulate-failure checkins.csv
# 预期：退出一行"数据读取失败：checkins.csv（该文件本次不参与判断）"，快照标 unavailable，不编造签到
```

---

## 5. 兼容性与演进

- 新增列：向后兼容，旧数据缺列按"缺失"处理。
- 改列名或语义：属破坏性变更，需同步 `data/` 样本、`tests/`、本文、`CHANGELOG.md`。
- 新增校验：必须同时在 `docs/design.md` §2 写清"拦的是什么失败"，并补单元测试。
- `FORBIDDEN_CAPABILITIES` 改动需审核与质量负责人书面同意（见 `CONTRIBUTING.md`）。
