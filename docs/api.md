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
| `shift_id` | str | 引用排班；找不到即"计划外到岗"（C1）——顶班也长这样，交给人认 |
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
"格式无法判定"**，不丢弃、不猜。责任人空的未结项会报"未结项归属缺失"；
同一个交接里 `OI-1` 出现两次会报**未结项编号重复**——不然"谁负责、结没结"就成了两说。

---

## 2. 输出

`write_outputs(result, out_dir)` 只写 `out/`，共 7 个文件（加 `--baseline` 再多 2 个，见 §2.3）：

| 文件 | 内容 | 谁看 |
|---|---|---|
| `items.md` | 一页缺项清单（Markdown） | 现场协调员 |
| `items.csv` | 同上，14 列，含双时间与 locator | 流程协调员 |
| `handover.md` | 交接责任清单 + 未结项 | 流程协调员 |
| `snapshots.csv` | 每个输入文件的 sha256、行数、读取状态 | 质量负责人 |
| `audit.csv` | 谁在什么时候读/导出/确认了什么 | 质量负责人 |
| `metrics.md` / `metrics.csv` | 误报率、确认率、复核滞后（分母是已复核数，见 §2.1） | 业务负责人 |
| `score.md` | 金标比对的召回率/精确率与 G1 判定（需 `--gold` 才生成） | 质量负责人 |
| `diff.md` / `diff.csv` | 与上一次运行的差异：新增/持续/消失（需 `--baseline` 才生成） | 流程协调员 |

`items.csv` 列顺序（14 列）：

```
编号, 校验, 类型, 对象, 事实, 业务发生时间, 系统接收时间, 依据版本, 来源位置, 建议, 复核状态, 复核人, 复核时间, 相关对象
```

`编号` 是**内容指纹**（`F-` + sha1 前 10 位），由 校验/类型/对象/来源位置/双时间/事实 算出。
不用序号，因为序号会随检查顺序变化，人工回填的复核结论就会挂到别的条目上。
代价是数据一改编号就变，旧结论对不上——这是故意的：数据变了就该重新确认。

`相关对象` 是机器可读的关联编号（目前只有 C2 占位冲突用它，形如 `S004,S005`），
金标比对靠它配对，人不用看。

### 2.1 复核回填：`data/review.csv`

清单发出去、人核完，结论必须回到系统里，否则"误报率"永远算不出来。

```csv
编号,复核状态,复核人,复核时间,备注
F-963f4385f1,已确认,唐映秋,2026-10-03T17:20:00,现场电话核实：志愿者被临时调去补给站
F-7843649eb4,已驳回,林亦舟,2026-10-03T17:41:00,录入笔误，两个时间戳被打反
```

硬规则（`core/review.py`）：

| 规则 | 不满足时 |
|---|---|
| `复核状态` 只能是 `已确认` / `已驳回` / `转人工队列` | 该行不生效，报"工具不替人做结论" |
| 必须有 `复核人` | 不生效——没人负责的结论不算确认（f22/f45） |
| 必须有 `复核时间` | 不生效——否则无法回答"压了多久还没核" |
| 编号重复 | 只认第一条，后一条报出来 |
| 编号对不上当前清单 | 不静默丢弃，提示"数据可能已变，需重新核对" |

指标口径（`core/metrics.py`）：

- **误报率** = 已驳回 / **已复核**。分母只含人实际核过的，未复核的不进分母、也不算误报。
- **确认率** = 已确认 / **全部条目**。试点硬门 100%：每条没确认的缺项在现场等于没人负责。
- **复核滞后** = 复核时间 − 本次运行时间。是滞后不是工时；为负时单独列出、不计入平均。

### 2.2 金标比对：`data/gold_overlap.csv`

```csv
shift_a,shift_b,是否真重叠,标注人,备注
S004,S005,是,傅景,同一替补被同时排在补给站与咨询台
S001,S003,否,傅景,同岗位不同人，连班不算冲突
```

- **召回** = 命中的真重叠 / 金标里全部真重叠。**这是关闭 G1 的唯一判别依据**（"发现全部重叠"需要分母）。
- **精确** = 命中 / 工具报出的（分母只算金标明确标过"否"的）。
- 工具报了、金标没标过这一对 → 记**金标未覆盖**，单独列出，**不算误报**。
  没标注不等于没异常；算成误报会让人误以为该收窄条件。
- `是否真重叠` 只认 是/否（及 y/n、true/false、1/0），其他取值报格式问题。

`来源位置` 形如 `shifts.csv#L5 + checkins.csv#L4`——`文件名#L物理行号`（首数据行为 `L2`）。
**每一条缺项都必须能靠这个坐标一跳回到原始行**，这是"可追溯"的验收方式。

---

### 2.3 批次对比：`--baseline`

```bash
# 昨天的清单做基线，今天的运行和它比
python3 -m volunteer_handover.main --out out --baseline data/prev/items.csv
```

比对键是 **「校验 + 类型 + 对象」**，不是 `编号`：编号是内容指纹，事实字段一改就换号，
拿它做键会把"同一件事补充了点位"读成"消失又新增"。编号变化单独标为 `持续（内容有变）`。

三种结论：

| 变化 | 含义 | 人的动作 |
|---|---|---|
| `新增` | 这次才有 | 当班人核对是不是真发生了 |
| `持续` | 上次也有，业务身份没变 | 接上次的复核结论，不必重新看 |
| `消失` | 上次有、这次没有 | **不代表已解决**：可能文件没读到、换了批次、或口径变了 |

`消失` 永远单独成组并带一句提醒，不并进"已整改"——把"没看见"当成"变好了"就是 F9 假状态。

同一组里可能有多条（一个交接有 OI-1、OI-2 两条逾期），所以配对是逐条的：
先按编号精确配，再按来源位置配，剩下的按顺序配；配不上的才算新增/消失。不会把两条并成一条。

### 2.4 配置契约

配置走白名单（`core/configschema.py` 的 `KNOWN`）：**未知键直接让运行 blocked**，并给出最像的键名。
理由：这个项目里"关掉一条校验"和"拼错一个键"在结果上长得一样——把
`require_confirm_status` 打成 `require_confirm_staus`，代码读到 `None`，那一整类异常就悄悄没了，
而清单看起来只是"干净了一些"。

| 段 | 允许的键 |
|---|---|
| `project` | `name` `version` `mode`（只能 `readonly`） |
| `pilot` | `batch_id` `desk_dry_run` `page_item_limit` `max_review_hours` |
| `scope` | `excluded_position_categories` `allowed_anomaly_types`（只能是 C1/C2 的异常类型） |
| `time` | `as_of` `backfill_threshold_minutes`（可为 null） |
| `versions` | `require_validity_window` `require_confirm_status` |
| `boundary` | `write_apis` `outbound_channel` `auto_assign_categories` |
| `output` | `dir` `max_page_items` |

同时校验类型（整数/布尔/列表/字符串）、正数范围、`time.as_of` 能否解析。
新增配置必须同时改 `configschema.KNOWN` 与 `config/default.yaml`，测试会盯着两边一致。

## 3. 模块接口

```python
from volunteer_handover.core.engine import run, write_outputs
from volunteer_handover.core import boundary, checks, fields, handover, ids, items, loader, times, trace
from volunteer_handover.utils import config, csvio, logutil
```

| 函数 / 类 | 签名 | 说明 |
|---|---|---|
| `run` | `run(data_dir, config=None, review_path=None, run_at="") -> RunResult` | 编排：加载 → 快照 → C1–C9 → 回填复核 → 算指标。不写文件 |
| `write_outputs` | `write_outputs(result, out_dir) -> list[Path]` | 只写 out/ |
| `RunResult` | `.items` `.checks` `.dataset` `.warnings` `.excluded_shifts` `.blocked` `.review` `.metrics` `.run_at` `.summary()` | `blocked` 为真表示能力越界或表头契约不满足，CLI 退出 2 |
| `loader.Dataset` | `.available(name)` `.blocked_columns()` `.column_warnings()` | 读到 0 行 ≠ 没读到；缺必需列 = 本趟不出结论 |
| `schema.check_columns` | `check_columns(file_name, header) -> ColumnCheck` | 必需列缺失 → blocked；可选列缺失 → 跳过对应判断并告警 |
| `review.load_reviews` / `apply_reviews` | `load_reviews(path) -> (entries, problems)`；`apply_reviews(findings, entries) -> ReviewApply` | 没复核人/没时间的结论不生效；对不上的编号显式报出 |
| `metrics.compute` | `compute(findings, run_at="") -> Metrics` | `.false_positive_rate` 无样本时为 `None`，不是 0 |
| `gold.score` | `score(gold_pairs, findings, code="C2") -> ScoreResult` | `.g1_ready` 为真才可以说"发现全部重叠" |
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
  --review FILE           人工复核回填表（如 data/review.csv）；给了才算误报率/确认率
  --gold FILE             金标标注表（如 data/gold_overlap.csv）；给了才算召回率
  --baseline FILE         上次运行的 items.csv；给了就出 diff.md/diff.csv（新增/持续/消失）
  --run-at ISO            清单生成时间；回放历史批次时给出，否则复核滞后会算出负数
  --simulate-failure FILE 故意让某个输入不可读，用于验收 C8（可重复）
  --version               版本号
```

两个独立脚本，读已经落盘的 CSV，不重跑核对：

```bash
python3 scripts/metrics.py --items out/items.csv --review data/review.csv \
    --run-at 2026-10-03T17:00:00 --out out/metrics.md
python3 scripts/score.py   --items out/items.csv --gold data/gold_overlap.csv --out out/score.md
```

**退出码**

| 码 | 含义 |
|---|---|
| `0` | 正常完成（含"有缺项"——有缺项是正常工作结果） |
| `2` | 运行被阻断（`blocked`）：配置里出现写回接口/外发通道/自动指派，**或**表头缺必需列（"本次不出结论"） |
| `3` | 仅 `scripts/score.py`：金标比对未通过（G1 还不能关），即召回 < 100% 或还有未标注对 |

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
