# Plan：每日投递统计与 HTML 日报

> 状态：待批准
> 日期：2026-10-29
> 上游产物：[intent.md](intent.md)（已确认）/ [spec.md](spec.md)（已确认）

## 改动文件总览（按实现顺序）

| # | 文件 | 动作 | 说明 |
|---|------|------|------|
| 1 | `config.py` | 修改 | 新增 `STATS_DIR` / `REPORTS_DIR` |
| 2 | `statslib.py` | **新增** | 记录 + 日报 + 半周总结 + 建议规则（纯标准库） |
| 3 | `bosslib.py` | 修改 | `pre_filter` 返回 `(bool, reason)` |
| 4 | `verify_flow.py` | 修改 | 适配 `pre_filter` 新签名 |
| 5 | `boss_auto.py` | 修改 | 事件点记录 + `try/finally` 收尾生成报告 |
| 6 | `.gitignore` | 修改 | 新增 `stats/`、`reports/` |
| 7 | `README.md` | 修改 | 文件结构表 + 统计说明 |

## 分步实现

### 第 1 步：`config.py` 加配置

文件末尾新增：

```python
# ---------- 统计与报告 ----------
# 每日统计 JSON 与 HTML 日报输出目录（相对项目根目录）
STATS_DIR = "stats"
REPORTS_DIR = "reports"
```

风险：无（纯新增）。

### 第 2 步：新增 `statslib.py`（本功能核心，独立可测）

纯标准库（`json` / `os` / `html` / `datetime`），对外 4 个函数：

1. `record(kind, item)`
   - `kind` ∈ `sent` / `resumed` / `skipped`；`item` 为 dict（title/city/salary，skipped 含 reason）
   - 按**当前日期**定位 `stats/YYYY-MM-DD.json`，不存在则初始化 `{"date", "target": None, "sent": [], "resumed": [], "skipped": []}`
   - 同 `(title, city)` 已存在则跳过（防重复卡片重复落盘）
   - 追加后整体写回；目录不存在则 `os.makedirs` 创建
   - 任何异常内部吞掉并 `print("stats-warn: ...")`，**绝不向主流程抛异常**
2. `set_target(date, target)`：更新当日 JSON 的 `target` 字段（幂等）
3. `render_daily(date=None)`：读当日 JSON → 写 `reports/YYYY-MM-DD.html`；文件不存在则不生成（不报错）
4. `render_halfweek(date=None)`：
   - 仅当 `date` 是周二（覆盖周一~周二）或周五（覆盖周三~周五）时生成
   - 输出 `reports/summary-YYYY-MM-DD.html`（以结束日命名）
   - 覆盖期某天无文件按空数据处理
5. 内部：HTML 模板（单文件、内联 CSS、无 JS）、分布统计、建议规则（spec 1.3 第 4 条）、`html.escape` 全量转义

**建议规则实现**（确定性、无数据时输出"样本不足，暂无建议"）：
- 跳过原因占比 > 30% 且 > 10 条 → 点名提示（原因 → 建议话术映射表，如 `pre-city` → "可考虑扩大 CITIES"）
- 单一 `jd-skill:X` 占跳过总数 > 20% → "大量岗位要求 X，可评估放宽该技能过滤"
- 投递城市 top1 占比提示；投递薪资区间提示（解析 `15-25K` 取上下限均值区间）
- 半周总结额外：逐日投递量对比（最多日 vs 最少日差 > 30% 时提示）

风险：无（新文件，不影响现有功能）。

### 第 3 步：`bosslib.py` 改 `pre_filter` 签名

`pre_filter(title, city, exp, salary="")` → 返回 `(bool, reason)`，按现有判断顺序：
`pre-skip-word` / `pre-job-type` / `pre-city` / `pre-grad-year` / `pre-exp` / `pre-salary`，通过返回 `(True, None)`。
判断逻辑**一行不动**，只在每个 `return False` 处补 reason、`return True` 改 `(True, None)`。

风险：**签名变更**，调用方只有 `boss_auto.py` 和 `verify_flow.py`（已 grep 确认无其他调用点）。

### 第 4 步：`verify_flow.py` 适配

`passed, _ = bl.pre_filter(...)`，其余不动；verify_flow **不接入统计**（它是链路验证，样本无意义）。

### 第 5 步：`boss_auto.py` 接入（改动最集中的一步）

1. `import statslib`
2. 事件点记录（与现有 print 行一一对应，dry 模式全部跳过）：
   - `st["sent"] += 1` 处 → `statslib.record("sent", {...})`
   - `resume-chat` 处 → `statslib.record("resumed", {...})`
   - `skip(no detail)` / `skip(pre)` / `skip(jd-...)` / `skip(no btn)` / `chat-fail` 处 → `statslib.record("skipped", {..., "reason": ...})`
   - `pre` 的 reason 用第 3 步 `pre_filter` 返回的细分值
3. 目标确定后 `statslib.set_target(today, target)`
4. **`try/finally` 收尾**：从 `d = bl.connect()` 起包到主循环结束；finally 中（dry 跳过、异常吞掉）：
   - `statslib.render_daily()`
   - `statslib.render_halfweek()`（内部自己判断周二/周五）
   - 注意现有 `already reached target` 的提前 `return` 也要落在 finally 覆盖范围内（spec：照常刷新，幂等）

风险：主循环结构改动，是**最容易出问题的一步**（见下）。

### 第 6 步：`.gitignore`

`state.json` 条目旁新增：

```
# 每日统计与报告（个人投递记录，不入库）
stats/
reports/
```

### 第 7 步：`README.md`

- 文件结构表加 `statslib.py`、`stats/`、`reports/`
- "注意"节补一句：跑完自动在 `reports/` 生成当天 HTML 日报（周二/周五另有半周总结），浏览器直接打开

## 可能破坏的已有功能

| 已有功能 | 破坏途径 | 防护 |
|---|---|---|
| `verify_flow.py` 链路验证 | `pre_filter` 签名变更 | 第 3、4 步同批改完，`py_compile` + dry 验证 |
| 打招呼主流程时序 | 第 5 步重排 `boss_auto.py` | 循环体逻辑零改动，只加 record 调用和 try/finally 包裹；record 内部吞异常 |
| `state.json` 去重 | 无（不碰 state 结构） | — |
| `--dry` 空跑 | 误写统计 | dry 分支跳过所有 record/render |

## 测试 / 验证命令

1. **语法**：`python -m py_compile config.py statslib.py bosslib.py verify_flow.py boss_auto.py`
2. **statslib 冒烟**（临时脚本放 `tmp/`，验证后删除）：
   - 伪造 30 条 sent + 40 条 skipped（含各 reason）写入 `stats/`
   - `render_daily()` → 断言 HTML 存在、含关键标题/转义后的岗位名
   - 构造周二日期 → `render_halfweek()` → 断言 `summary-*.html` 存在且覆盖两天
   - 周五日期、周一日期（应不生成）各验证一次
   - 建议规则：构造 `pre-city` 占 40% 的数据，断言建议文本出现
3. **真机 dry 跑**（设备在线时）：`python -u boss_auto.py --dry` → 确认无 `stats/` 写入、无报告生成、流程正常
4. **真机实跑**（用户执行）：`python -u boss_auto.py` → 跑完打开 `reports/当天.html` 核对数据与终端日志一致

## 最容易出问题的步骤 & 备选方案

1. **第 5 步 `boss_auto.py` 的 try/finally 重排**——现有代码有多个提前 `return`（目标已达成、`ensure_list_page` 抛 RuntimeError），包错范围会导致"中断不刷新报告"或"报告重复生成"。
   - 对策：finally 只放幂等的 render 调用；改完逐条对照原 return 路径。
   - 备选：不重排结构，改为在**每个** return/循环出口手动调 `statslib.finish()`——调用点多易漏，不推荐。
2. **`pre_filter` 签名变更**——若漏改调用点会直接 `TypeError`。
   - 已确认仅 2 个调用点；`py_compile` 挡不住运行时错误，靠第 3 条 dry 跑兜底。
   - 备选：保留旧签名、另加 `pre_filter_reason()` 只算原因——逻辑双份易漂移，不推荐。
3. **半周边界判断**（周二/周五、覆盖期起止）——off-by-one 风险。
   - 对策：冒烟测试显式覆盖周二/周五/周一三个日期。

## 提交计划（用户要求时执行）

按仓库风格（conventional + 中文）拆 2 个提交：
1. `feat(stats): 新增每日投递/跳过统计与 HTML 日报模块`（config.py + statslib.py + .gitignore）
2. `feat(stats): 主流程接入统计记录并自动生成日报/半周总结`（bosslib.py + verify_flow.py + boss_auto.py + README.md）

（`docs/sdlc/daily-stats/` 三份产物随第 1 个提交入库。）
