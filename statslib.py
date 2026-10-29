# -*- coding: utf-8 -*-
"""statslib：每日投递统计与 HTML 日报（纯标准库，无设备操作）。

职责：
  record(kind, item)     主循环事件点追加记录到 stats/YYYY-MM-DD.json
  set_target(target)     记录当日随机目标
  render_daily(date)     生成/刷新当天 HTML 日报
  render_overview()      聚合全部 stats/*.json 生成跨天总览 overview.html
  render_halfweek(date)  周二（周一~周二）/ 周五（周三~周五）生成半周总结
  finish()               运行收尾：日报 + 总览 + 半周总结

所有函数都不向调用方抛异常（失败只打印 stats-warn 警告，不影响主流程）。
"""
import datetime
import html
import json
import os
import re
from collections import Counter

import config as C

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATS_DIR = os.path.join(BASE_DIR, C.STATS_DIR)
REPORTS_DIR = os.path.join(BASE_DIR, C.REPORTS_DIR)

_SALARY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[-~～]\s*(\d+(?:\.\d+)?)\s*[Kk千]")

# 跳过原因 -> 建议话术（jd-skill:* 单独处理）
_REASON_ADVICE = {
    "pre-skip-word": "标题排除词（SKIP_WORDS）命中较多，检查是否过宽",
    "pre-job-type": "非技术岗黑名单（SKIP_JOB_TYPES）命中较多，若误杀可调整",
    "pre-city": "城市过滤占比高，若目标城市岗位偏少可考虑扩大 CITIES",
    "pre-grad-year": "届别过滤占比高，推荐流中其他届别岗位多（通常属正常，可忽略）",
    "pre-exp": "经验要求过滤占比高，推荐流中 1 年以上经验岗位多（通常属正常，可忽略）",
    "pre-salary": "薪资超线（MAX_SALARY_K）过滤占比高，可评估是否偏严",
    "no-detail": "详情页打开失败较多，检查真机网络/状态",
    "no-btn": "找不到打招呼按钮较多，留意 App 改版或风控",
    "chat-fail": "打招呼后未进聊天页较多，留意账号状态/风控",
}

_CSS = """
body { font-family: "Microsoft YaHei", "Segoe UI", sans-serif; margin: 0;
       background: #f5f6f8; color: #24292f; }
.wrap { max-width: 960px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 22px; margin: 0 0 4px; }
.sub { color: #57606a; font-size: 13px; margin-bottom: 20px; }
.cards { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 8px; }
.card { background: #fff; border-radius: 8px; padding: 14px 18px; min-width: 120px;
        box-shadow: 0 1px 2px rgba(0,0,0,.06); }
.card .num { font-size: 26px; font-weight: 700; }
.card .lbl { font-size: 12px; color: #57606a; margin-top: 2px; }
h2 { font-size: 16px; margin: 24px 0 8px; }
table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px;
        overflow: hidden; box-shadow: 0 1px 2px rgba(0,0,0,.06); font-size: 13px; }
th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid #eaecef; }
th { background: #f6f8fa; color: #57606a; font-weight: 600; }
tr:last-child td { border-bottom: none; }
.reason { color: #b35900; }
.advice { background: #fff; border-left: 4px solid #0969da; border-radius: 6px;
          padding: 12px 16px; font-size: 14px; line-height: 1.7;
          box-shadow: 0 1px 2px rgba(0,0,0,.06); }
.advice li { margin: 4px 0; }
.muted { color: #8b949e; }
a { color: #0969da; text-decoration: none; }
a:hover { text-decoration: underline; }
.trend { background: #fff; border-radius: 8px; padding: 16px;
         box-shadow: 0 1px 2px rgba(0,0,0,.06); }
.trow { display: flex; align-items: center; gap: 10px; margin: 5px 0; font-size: 12px; }
.trow .tdate { width: 92px; color: #57606a; flex-shrink: 0; }
.tbar { height: 14px; background: #0969da; border-radius: 3px; }
.trow .tval { color: #57606a; flex-shrink: 0; }
.jd-toggle { display: none; }
.jd-btn { cursor: pointer; font-size: 12px; color: #0969da; user-select: none;
          display: inline-flex; align-items: center; gap: 5px; font-weight: 600; }
.jd-btn::before { content: "＋"; font-size: 13px; line-height: 1; }
tr.main:has(.jd-toggle:checked) .jd-btn::before { content: "－"; }
tr.detail { display: none; }
tr.main:has(.jd-toggle:checked) + tr.detail { display: table-row; }
tr.main:has(.jd-toggle:checked) > td { border-bottom: none; }
tr.detail > td { background: #f6f8fa; padding: 12px 16px;
                 border-bottom: 1px solid #eaecef; }
.jpanel .jmeta { font-size: 12px; color: #57606a; margin-bottom: 8px; }
.jpanel .jtext { font-size: 13px; line-height: 1.7; white-space: pre-wrap;
                 word-break: break-word; color: #444c56; background: #fff;
                 border: 1px solid #eaecef; border-radius: 8px; padding: 12px 14px;
                 box-shadow: 0 1px 2px rgba(0,0,0,.04); }
"""


def _today():
    return datetime.date.today().strftime("%Y-%m-%d")


def _stats_path(date):
    return os.path.join(STATS_DIR, date + ".json")


def _load_day(date):
    try:
        with open(_stats_path(date), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _new_day(date):
    return {"date": date, "target": None, "sent": [], "resumed": [], "skipped": []}


def _save_day(date, day):
    os.makedirs(STATS_DIR, exist_ok=True)
    with open(_stats_path(date), "w", encoding="utf-8") as f:
        json.dump(day, f, ensure_ascii=False, indent=1)


# ---------- 记录 ----------

def record(kind, item):
    """追加一条记录（kind: sent/resumed/skipped）。同 (title,city) 不重复。"""
    try:
        if kind not in ("sent", "resumed", "skipped"):
            return
        date = _today()
        day = _load_day(date) or _new_day(date)
        rec = {"title": item.get("title", ""),
               "city": item.get("city", ""),
               "salary": item.get("salary", ""),
               "time": datetime.datetime.now().strftime("%H:%M:%S")}
        # 透传详情页附加信息（经验要求 / JD 全文 / 失败页面），有才记
        for k in ("exp", "jd", "fail_act"):
            if item.get(k):
                rec[k] = item[k]
        if kind == "skipped":
            rec["reason"] = item.get("reason", "unknown")
        if any(r.get("title") == rec["title"] and r.get("city") == rec["city"]
               for r in day.get(kind, [])):
            return
        day.setdefault(kind, []).append(rec)
        _save_day(date, day)
    except Exception as e:
        print("stats-warn(record): %s" % e)


def set_target(target):
    """记录当日随机目标（多次运行以最后一次为准）。"""
    try:
        date = _today()
        day = _load_day(date) or _new_day(date)
        day["target"] = int(target)
        _save_day(date, day)
    except Exception as e:
        print("stats-warn(target): %s" % e)


# ---------- 报告 ----------

def _esc(s):
    return html.escape(str(s))


# 跳过原因代码 -> 中文显示（仅展示层；JSON 仍存原始代码）
_REASON_ZH = {
    "pre-skip-word": "标题排除词",
    "pre-job-type": "非技术岗",
    "pre-city": "城市不符",
    "pre-grad-year": "届别不符",
    "pre-exp": "经验要求不符",
    "pre-salary": "薪资超上限",
    "no-detail": "详情页打开失败",
    "no-btn": "未找到打招呼按钮",
    "chat-fail": "打招呼未进聊天页",
}


def _reason_zh(reason):
    reason = reason or "unknown"
    if reason.startswith("jd-skill:"):
        return "技能要求: %s" % reason.split(":", 1)[1]
    return _REASON_ZH.get(reason, reason)


def _advice(days, is_halfweek):
    """基于记录数据生成改进建议（确定性规则；无数据时提示样本不足）。"""
    sent = [r for _, d in days for r in (d or {}).get("sent", [])]
    skipped = [r for _, d in days for r in (d or {}).get("skipped", [])]
    out = []

    total_sk = len(skipped)
    if total_sk:
        rc = Counter(r.get("reason", "unknown") for r in skipped)
        done = set()
        # 规则 1：某原因占比 > 30% 且 > 10 条
        for reason, cnt in rc.most_common():
            if cnt > 10 and cnt * 1.0 / total_sk > 0.3:
                pct = cnt * 100.0 / total_sk
                if reason.startswith("jd-skill:"):
                    out.append("大量岗位要求「%s」（%d 条，占跳过 %.0f%%），"
                               "可评估是否放宽该技能过滤或补充技能"
                               % (reason.split(":", 1)[1], cnt, pct))
                else:
                    out.append("%s（%d 条，占跳过 %.0f%%）"
                               % (_REASON_ADVICE.get(reason, "该类跳过占比偏高"), cnt, pct))
                done.add(reason)
        # 规则 2：单一硬技能占跳过 > 20%（阈值更低，未命中规则 1 时补上）
        for reason, cnt in rc.most_common():
            if reason in done or not reason.startswith("jd-skill:"):
                continue
            if cnt * 1.0 / total_sk > 0.2:
                out.append("较多岗位要求「%s」（%d 条，占跳过 %.0f%%），"
                           "可评估是否放宽该技能过滤或补充技能"
                           % (reason.split(":", 1)[1], cnt, cnt * 100.0 / total_sk))
                done.add(reason)

    if sent:
        # 城市分布（top3 信息行 + 单城市集中预警）
        cc = Counter(r.get("city") or "未知" for r in sent)
        top3 = "、".join("%s %d" % (k, v) for k, v in cc.most_common(3))
        out.append("投递城市分布：%s（共 %d 条）" % (top3, len(sent)))
        top_city, top_cnt = cc.most_common(1)[0]
        if top_cnt * 1.0 / len(sent) > 0.5:
            out.append("投递集中于 %s（%.0f%%），注意单城市竞争/风控风险"
                       % (top_city, top_cnt * 100.0 / len(sent)))
        # 薪资区间
        los, his = [], []
        for r in sent:
            m = _SALARY_RE.search(r.get("salary") or "")
            if m:
                los.append(float(m.group(1)))
                his.append(float(m.group(2)))
        if los:
            out.append("投递岗位月薪区间约 %dK ~ %dK" % (min(los), max(his)))

    if is_halfweek:
        # 逐日投递量对比（最大/最小差 > 30% 时提示）
        per_day = [(date, len((d or {}).get("sent", []))) for date, d in days]
        vals = [v for _, v in per_day]
        if vals and min(vals) > 0 and (max(vals) - min(vals)) * 1.0 / max(vals) > 0.3:
            hi = max(per_day, key=lambda x: x[1])
            lo = min(per_day, key=lambda x: x[1])
            out.append("%s 投递 %d 条 vs %s 仅 %d 条，推荐流供给差异大，"
                       "可对比两日时段/城市差异" % (hi[0], hi[1], lo[0], lo[1]))

    if not out:
        out.append("样本不足，暂无建议")
    return out


def _build_html(title, subtitle, days, with_trend):
    """days: [(date, day_dict|None)]；with_trend: 半周总结显示逐日趋势。"""
    sent_all = [(date, r) for date, d in days for r in (d or {}).get("sent", [])]
    resumed_all = [r for _, d in days for r in (d or {}).get("resumed", [])]
    skipped_all = [(date, r) for date, d in days for r in (d or {}).get("skipped", [])]
    targets = [d.get("target") for _, d in days if d and d.get("target")]
    target = sum(targets) if targets else None

    # 概览卡片
    cards = [("投递", str(len(sent_all))),
             ("跳过", str(len(skipped_all))),
             ("已有会话", str(len(resumed_all)))]
    if target:
        pct = min(100, int(len(sent_all) * 100.0 / target))
        cards.append(("目标达成", "%d%%" % pct))
    cards_html = "".join(
        '<div class="card"><div class="num">%s</div><div class="lbl">%s%s</div></div>'
        % (_esc(v), _esc(k), "（目标 %d）" % target if k == "目标达成" else "")
        for k, v in cards)

    # 跳过原因分布
    rc = Counter(r.get("reason", "unknown") for _, r in skipped_all)
    if skipped_all:
        reason_rows = "".join(
            "<tr><td class='reason'>%s</td><td>%d</td><td>%.1f%%</td></tr>"
            % (_esc(_reason_zh(k)), v, v * 100.0 / len(skipped_all))
            for k, v in rc.most_common())
        reason_html = "<table><tr><th>原因</th><th>数量</th><th>占比</th></tr>%s</table>" % reason_rows
    else:
        reason_html = '<p class="muted">无跳过记录</p>'

    # 逐日趋势（半周总结）
    trend_html = ""
    if with_trend:
        rows = "".join(
            "<tr><td>%s</td><td>%d</td><td>%d</td><td>%d</td></tr>"
            % (_esc(date), len((d or {}).get("sent", [])),
               len((d or {}).get("skipped", [])), len((d or {}).get("resumed", [])))
            for date, d in days)
        trend_html = ("<h2>逐日概览</h2><table>"
                      "<tr><th>日期</th><th>投递</th><th>跳过</th><th>已有会话</th></tr>%s</table>"
                      % rows)

    # 投递/跳过清单：JD 列放开关，点击在该行下方展开整行详情面板
    date_th = "<th>日期</th>" if with_trend else ""
    _seq = [0]

    def _jd_toggle_cell(r):
        jd = (r.get("jd") or "").strip()
        if not jd:
            return '<td><span class="muted">-</span></td>'
        _seq[0] += 1
        cid = "jd%d" % _seq[0]
        return ('<td><input type="checkbox" class="jd-toggle" id="%s">'
                '<label for="%s" class="jd-btn">JD</label></td>' % (cid, cid))

    def _detail_row(r, ncols, extra=""):
        jd = (r.get("jd") or "").strip()
        if not jd:
            return ""
        meta = " · ".join(x for x in [
            _esc(r.get("title")), _esc(r.get("city")),
            _esc(r.get("exp")) if r.get("exp") else None,
            _esc(r.get("salary")) if r.get("salary") else None,
            extra] if x)
        return ('<tr class="detail"><td colspan="%d"><div class="jpanel">'
                '<div class="jmeta">%s</div>'
                '<div class="jtext">%s</div></div></td></tr>'
                % (ncols, meta, _esc(jd)))

    if sent_all:
        ncol = 6 + (1 if with_trend else 0)
        sent_rows = "".join(
            ('<tr class="main">%s<td>%s</td><td>%s</td><td>%s</td>'
             '<td>%s</td><td>%s</td>%s</tr>%s')
            % (("<td>%s</td>" % _esc(date)) if with_trend else "",
               _esc(r.get("time")), _esc(r.get("title")), _esc(r.get("city")),
               _esc(r.get("exp") or "-"), _esc(r.get("salary")),
               _jd_toggle_cell(r), _detail_row(r, ncol))
            for date, r in sent_all)
        sent_html = ("<table><tr>%s<th>时间</th><th>岗位</th><th>城市</th>"
                     "<th>经验要求</th><th>薪资</th><th>JD</th></tr>%s</table>"
                     % (date_th, sent_rows))
    else:
        sent_html = '<p class="muted">无投递记录</p>'

    # 跳过清单
    if skipped_all:
        ncol = 6 + (1 if with_trend else 0)
        skip_rows = "".join(
            ('<tr class="main">%s<td>%s</td><td>%s</td><td>%s</td>'
             '<td>%s</td><td class="reason">%s</td>%s</tr>%s')
            % (("<td>%s</td>" % _esc(date)) if with_trend else "",
               _esc(r.get("time")), _esc(r.get("title")), _esc(r.get("city")),
               _esc(r.get("exp") or "-"), _esc(_reason_zh(r.get("reason"))),
               _jd_toggle_cell(r),
               _detail_row(r, ncol, extra="原因：" + _esc(_reason_zh(r.get("reason")))))
            for date, r in skipped_all)
        skip_html = ("<table><tr>%s<th>时间</th><th>岗位</th><th>城市</th>"
                     "<th>经验要求</th><th>原因</th><th>JD</th></tr>%s</table>"
                     % (date_th, skip_rows))
    else:
        skip_html = '<p class="muted">无跳过记录</p>'

    # 建议
    adv = _advice(days, with_trend)
    advice_html = ('<div class="advice"><ul>%s</ul></div>'
                   % "".join("<li>%s</li>" % _esc(a) for a in adv))

    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s</title>
<style>%s</style>
</head>
<body>
<div class="wrap">
<h1>%s</h1>
<div class="sub">%s · <a href="overview.html">总览</a></div>
<div class="cards">%s</div>
%s
<h2>跳过原因分布</h2>
%s
<h2>投递清单（%d）</h2>
%s
<h2>跳过清单（%d）</h2>
%s
<h2>改进建议</h2>
%s
</div>
</body>
</html>
""" % (_esc(title), _CSS, _esc(title), _esc(subtitle), cards_html,
       trend_html, reason_html, len(sent_all), sent_html,
       len(skipped_all), skip_html, advice_html)


def _write_report(path, html_text):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_text)
    return path


def render_daily(date=None):
    """生成/刷新当天日报 reports/YYYY-MM-DD.html；无数据返回 None。"""
    date = date or _today()
    day = _load_day(date)
    if day is None:
        return None
    path = _write_report(
        os.path.join(REPORTS_DIR, date + ".html"),
        _build_html("投递日报 · %s" % date,
                    "自动生成 · 数据来源 stats/%s.json" % date,
                    [(date, day)], False))
    print("report: %s" % os.path.relpath(path, BASE_DIR))
    return path


def render_halfweek(date=None):
    """周二结束（覆盖周一~周二）/ 周五结束（覆盖周三~周五）生成半周总结。

    其他日期不生成，返回 None；覆盖期某天无数据按空处理。
    """
    d = datetime.date.fromisoformat(date) if date else datetime.date.today()
    if d.weekday() == 1:      # 周二
        start = d - datetime.timedelta(days=1)
    elif d.weekday() == 4:    # 周五
        start = d - datetime.timedelta(days=2)
    else:
        return None
    days = []
    for i in range((d - start).days + 1):
        ds = (start + datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        days.append((ds, _load_day(ds)))
    path = _write_report(
        os.path.join(REPORTS_DIR, "summary-" + d.strftime("%Y-%m-%d") + ".html"),
        _build_html("半周总结 · %s ~ %s" % (days[0][0], days[-1][0]),
                    "自动生成 · 覆盖 %d 天" % len(days), days, True))
    print("report: %s" % os.path.relpath(path, BASE_DIR))
    return path


def render_overview():
    """聚合全部 stats/*.json 生成跨天总览 reports/overview.html。

    汇总卡片 + 逐日投递趋势（纯 CSS 条形图）+ 每日明细表；无数据返回 None。
    """
    try:
        os.makedirs(STATS_DIR, exist_ok=True)
        days = []
        for fn in sorted(os.listdir(STATS_DIR)):
            if fn.endswith(".json"):
                ds = fn[:-5]
                day = _load_day(ds)
                if day is not None:
                    days.append((ds, day))
        if not days:
            return None
        path = _write_report(
            os.path.join(REPORTS_DIR, "overview.html"),
            _build_overview(days))
        print("report: %s" % os.path.relpath(path, BASE_DIR))
        return path
    except Exception as e:
        print("stats-warn(overview): %s" % e)


def _build_overview(days):
    """days: [(date, day_dict)] 升序；返回总览 HTML。"""
    sent_all = [r for _, d in days for r in (d or {}).get("sent", [])]
    skipped_all = [r for _, d in days for r in (d or {}).get("skipped", [])]
    resumed_all = [r for _, d in days for r in (d or {}).get("resumed", [])]
    targets = [d.get("target") for _, d in days if d and d.get("target")]
    target_sum = sum(targets) if targets else None
    n = len(days)

    cards = [("天数", str(n)),
             ("总投递", str(len(sent_all))),
             ("日均投递", "%.1f" % (len(sent_all) * 1.0 / n)),
             ("总跳过", str(len(skipped_all))),
             ("已有会话", str(len(resumed_all)))]
    if target_sum:
        cards.append(("整体达成", "%d%%" % min(100, int(len(sent_all) * 100.0 / target_sum))))
    cards_html = "".join(
        '<div class="card"><div class="num">%s</div><div class="lbl">%s</div></div>'
        % (_esc(v), _esc(k)) for k, v in cards)

    # 逐日投递趋势（纯 CSS 条形图）
    max_sent = max([len((d or {}).get("sent", [])) for _, d in days] + [1])
    bars = "".join(
        '<div class="trow"><span class="tdate">%s</span>'
        '<div class="tbar" style="width:%dpx"></div>'
        '<span class="tval">%d</span></div>'
        % (_esc(ds), max(2, int(len((d or {}).get("sent", [])) * 480.0 / max_sent)),
           len((d or {}).get("sent", [])))
        for ds, d in days)
    trend_html = '<div class="trend">%s</div>' % bars

    # 每日明细表
    rows = []
    for ds, d in days:
        s = len((d or {}).get("sent", []))
        k = len((d or {}).get("skipped", []))
        t = (d or {}).get("target")
        pct = ("%.0f%%" % min(100, s * 100.0 / t)) if t else "-"
        rc = Counter(r.get("reason", "unknown") for r in (d or {}).get("skipped", []))
        top = rc.most_common(1)[0][0] if rc else "-"
        rows.append(
            "<tr><td><a href='%s.html'>%s</a></td><td>%d</td><td>%d</td>"
            "<td>%s</td><td>%s</td><td class='reason'>%s</td></tr>"
            % (_esc(ds), _esc(ds), s, k, t if t else "-", pct,
               _esc(_reason_zh(top))))
    table_html = ("<table><tr><th>日期</th><th>投递</th><th>跳过</th><th>目标</th>"
                  "<th>达成率</th><th>Top 跳过原因</th></tr>%s</table>" % "".join(rows))

    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>投递总览</title>
<style>%s</style>
</head>
<body>
<div class="wrap">
<h1>投递总览</h1>
<div class="sub">自动生成 · 聚合 stats/ 全部 %d 天数据</div>
<div class="cards">%s</div>
<h2>逐日投递趋势</h2>
%s
<h2>每日明细</h2>
%s
</div>
</body>
</html>
""" % (_CSS, n, cards_html, trend_html, table_html)


def finish():
    """运行收尾：刷新当天日报 + 跨天总览，周二/周五追加半周总结。异常吞掉。"""
    try:
        render_daily()
        render_overview()
        render_halfweek()
    except Exception as e:
        print("stats-warn(finish): %s" % e)
