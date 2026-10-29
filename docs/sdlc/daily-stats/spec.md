# Spec：每日投递统计与 HTML 日报

> 状态：待确认
> 日期：2026-10-29
> 上游产物：[intent.md](intent.md)（已确认）

## 1. 功能如何工作

### 1.1 记录（写入侧）

在 `boss_auto.py` 主循环的每个事件点，把一条记录追加到当日统计文件 `stats/YYYY-MM-DD.json`：

| 事件点（现有日志行） | 记录到 | reason |
|---|---|---|
| `sent N/M: ...`（立即沟通成功） | `sent` | — |
| `resume-chat(不计): ...`（继续沟通，已有会话） | `resumed` | — |
| `skip(no detail): ...`（详情页打不开） | `skipped` | `no-detail` |
| `skip(pre): ...`（前置过滤） | `skipped` | 细分原因（见 1.2） |
| `skip(jd-<技能>): ...`（JD 缺硬技能） | `skipped` | `jd-skill:<技能名>` |
| `skip(no btn): ...`（找不到打招呼按钮） | `skipped` | `no-btn` |
| `chat-fail: ...`（点了按钮但没进聊天页） | `skipped` | `chat-fail` |

每条记录字段：`title` / `city` / `salary` / `time`（HH:MM:SS）/（skipped 另有 `reason`）。
详情页能读到的附加信息一并落盘（有才记，读不到不写该键）：
- `exp`：经验要求（详情页 `tv_required_work_exp`），`pre-*` 及之后的所有事件点都有
- `jd`：完整 JD 文本（`tv_description`），仅进入 JD 读取之后的事件点有（`jd-skill:*` / `no-btn` / `sent` / `resumed` / `chat-fail`）
- `fail_act`：`chat-fail` 时点击后停留的页面 activity，便于定位卡在哪
`no-detail` 未进详情页、`pre-*` 在读 JD 前被过滤，这两类拿不到 `jd`，属流程上限。
- 记录按**事件发生时的日期**归入对应天文件（跨天运行不会串天）。
- 同一天内同一 `(title, city)` 只记一次（与 `seen` 去重语义一致，防止重复卡片重复落盘）。
- `--dry` 空跑**不记录**（不点详情、不打招呼，数据无意义）。
- 写入方式：读当日 JSON → 追加 → 整体写回（单进程，无并发；文件小，无性能问题）。

### 1.2 pre_filter 细分原因

`bosslib.pre_filter` 目前只返回 `bool`，改为返回 `(passed: bool, reason: str|None)`，按现有判断顺序映射：

| 现有判断 | reason |
|---|---|
| 标题含 `SKIP_WORDS` | `pre-skip-word` |
| 标题含 `SKIP_JOB_TYPES` | `pre-job-type` |
| 城市不在 `CITIES` | `pre-city` |
| 届别不是 27 届 | `pre-grad-year` |
| 经验要求 1 年以上 | `pre-exp` |
| 经验不限但月薪上限超 `MAX_SALARY_K` | `pre-salary` |

通过时返回 `(True, None)`。`verify_flow.py` 同步适配新签名（只取第一个值，不记录统计）。

### 1.3 报告（读取侧）

新模块 `statslib.py`（标准库实现，无新依赖）：

1. **日报** `reports/YYYY-MM-DD.html`：每次 `boss_auto.py` 运行结束时生成/覆盖。
   - 主循环用 `try/finally` 包裹：正常结束、异常、Ctrl+C 中断都会走到 finally，基于**已落盘的全部记录**重新生成当天 HTML（即"中断后补在后面"——记录在 JSON 里已追加，报告在下次任何一次运行结束时刷新；中断当下也刷新一次）。
2. **半周总结** `reports/summary-YYYY-MM-DD.html`（以半周**结束日**命名）：
   - 当天是**周二**且跑完 → 生成覆盖 周一~周二 的总结；
   - 当天是**周五**且跑完 → 生成覆盖 周三~周五 的总结。
   - 覆盖期内某天没有数据文件时，该天按 0 展示（不报错）。
3. **HTML 形态**：单文件、内联 CSS、无 JS、无 CDN 依赖，浏览器直接打开。内容：
   - 概览卡片：投递数 / 跳过数 / 已有会话数 / 当日目标与达成情况
   - 跳过原因分布表（原因 → 数量 → 占比）
   - 投递清单表（时间 / 标题 / 城市 / 薪资）
   - 跳过清单表（时间 / 标题 / 城市 / 薪资 / 原因）
   - 改进建议区（见 1.4）
   - 半周总结额外：逐日投递/跳过趋势表 + 跨天汇总的原因分布
4. **建议规则**（确定性规则，输出中文短句列表；无数据时显示"样本不足，暂无建议"）：
   - 日报（**只用当天数据**）：
     - 某跳过原因占比 > 30% 且 > 10 条 → 点名该原因（如"35% 被城市过滤，若上海/苏州岗位多可考虑扩大 CITIES"）
     - 某单一硬技能（`jd-skill:X`）占跳过总数 > 20% → "大量岗位要求 X，可评估是否放宽该技能过滤或补充技能"
     - 投递城市分布 → 占比最高城市提示
     - 投递薪资分布 → 提示投递岗位薪资区间
   - 半周总结（用汇总数据）：同上规则跑在汇总数据上 + 逐日投递量对比（如"周三 118 条 vs 周五 62 条，周五推荐流偏少"）。
   - 建议**只给方向**，不自动改 config（intent 已确认）。

## 2. 数据如何流动

```
boss_auto.py 主循环
  ├─ 事件发生 ──> statslib.record(date, kind, item)  ──追加──> stats/YYYY-MM-DD.json
  └─ 运行结束(finally)
       ├─ statslib.render_daily(date)      ──读当日 JSON──> reports/YYYY-MM-DD.html
       └─ 周二/周五: statslib.render_halfweek(end_date)
            └── 读覆盖期各天 JSON ──> reports/summary-YYYY-MM-DD.html
```

- 数据单向：主循环只 `record`，报告只读 JSON，报告生成失败**不影响**主流程（try/except 包住，打印警告）。
- `state.json` 保持原样（当日去重 + sent 计数），与 `stats/` 职责分离：前者管"今天别重复"，后者管"留档回顾"。

## 3. 数据模型

`stats/2026-10-29.json`：

```json
{
  "date": "2026-10-29",
  "target": 120,
  "sent":    [{"title": "Java后端", "city": "上海", "salary": "15-25K", "time": "10:32:11",
               "exp": "经验不限", "jd": "岗位职责…\n任职要求…"}],
  "resumed": [{"title": "Python开发", "city": "苏州", "salary": "12-20K", "time": "10:41:02",
               "exp": "经验不限", "jd": "…"}],
  "skipped": [{"title": "Go开发", "city": "上海", "salary": "20-35K", "time": "10:45:30",
               "exp": "经验不限", "jd": "…", "reason": "jd-skill:Rust/Go"}]
}
```

（`target` 取当天运行时的随机目标，便于报告展示达成率；多次运行以最后一次为准。）

## 4. 影响哪些系统

| 文件 | 改动 |
|---|---|
| `bosslib.py` | `pre_filter` 返回 `(bool, reason)` —— **签名变更** |
| `verify_flow.py` | 适配 `pre_filter` 新签名（不接入统计） |
| `boss_auto.py` | 各事件点调用 `statslib.record`；主循环 `try/finally` 收尾生成报告 |
| `statslib.py`（新增） | 记录 + 日报 + 半周总结 + 建议规则 |
| `config.py` | 新增 `STATS_DIR` / `REPORTS_DIR`（默认项目根下 `stats/`、`reports/`） |
| `.gitignore` | 新增 `stats/`、`reports/`（已确认不入库） |
| `README.md` | 文件结构表 + 用法补充 |

不改动：`state.json` 结构、打招呼流程、所有设备操作函数。

## 5. 安全 / 合规 / 性能疑点

- **隐私**：`stats/` 含个人投递明细，已确认 gitignore 不入库；HTML 报告同目录同样不入库。
- **风控**：统计全程不新增任何 App 页面操作（不读聊天页、不点消息 tab），只在现有事件点落盘，风控暴露面不变。
- **依赖**：仅 Python 标准库（`json` / `html` / `datetime` / `os`），不新增第三方包。
- **性能**：每天 ~120 条投递 + 数百条跳过，JSON 读写与 HTML 渲染均可忽略不计；报告生成在 finally 中，最多多花 <1s。
- **失败隔离**：记录/报告任何异常只打印警告，不中断打招呼主流程。
- **HTML 注入**：岗位标题来自 App 文本，渲染时统一 `html.escape`。

## 6. 边界情况

| 场景 | 行为 |
|---|---|
| 运行跨天（23:59 开始） | 记录按事件发生日期归天，两边各归各的 |
| 中途 Ctrl+C / 异常 | finally 刷新当天报告；已落盘记录不丢 |
| 当天已达目标提前退出（`already reached target`） | 照常刷新当天报告（数据无变化，幂等） |
| 周二/周五没跑 | 不生成半周总结（下次跑周二/周五才生成） |
| 半周覆盖期某天无数据 | 该天按 0 展示 |
| 旧 `state.json` 首次升级 | 无迁移：stats 从升级当天开始记录，历史不可追溯（可接受） |
