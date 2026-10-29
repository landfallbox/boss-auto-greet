# -*- coding: utf-8 -*-
"""bosslib：BOSS 直聘设备操作共享模块（无主循环）。

boss_auto.py 与 verify_flow.py 共用这里的函数，避免重复代码。
所有可调参数从 config 读取。
"""
import re
import subprocess
import time

import uiautomator2 as u2

import config as C


def connect():
    """连接真机，返回 uiautomator2 Device 对象"""
    return u2.connect(C.SERIAL)


def adb_shell(cmd):
    subprocess.run(["adb", "-s", C.SERIAL, "shell", cmd],
                   capture_output=True, timeout=30)


_FOCUS_RE = re.compile(r"mCurrentFocus=Window\{[^}]*?u(\d+)\s+([\w.]+)/([\w.]+)\}")


def app_current(d):
    """读当前前台 App：直接解析 `dumpsys window` 的 mCurrentFocus。

    uiautomator2 的 app_current() 依赖 `dumpsys window windows`，
    但 MIUI + XSpace 双开下该命令不含 mCurrentFocus，会回退到
    `dumpsys activity top` 误读后台 App；`dumpsys window` 才是可靠的。
    """
    out = subprocess.run(["adb", "-s", C.SERIAL, "shell", "dumpsys", "window"],
                         capture_output=True, timeout=30).stdout.decode("utf-8", "ignore")
    m = _FOCUS_RE.search(out)
    if m:
        return {"package": m.group(2), "activity": m.group(3)}
    return d.app_current()


def current_activity(d):
    return app_current(d).get("activity", "")


# ---------- 页面导航 ----------

def ensure_list_page(d):
    """确保在职位推荐列表页（MainActivity）"""
    d.screen_on()
    time.sleep(1)
    cur = app_current(d)
    if cur.get("package") != C.PKG:
        adb_shell("am start --user %d -n %s/%s" % (C.USER, C.PKG, C.LAUNCH_ACT))
        time.sleep(10)
    for _ in range(3):
        if C.MAIN_ACT in current_activity(d):
            break
        d.press("back")
        time.sleep(C.BACK_WAIT)
    if C.MAIN_ACT not in current_activity(d):
        raise RuntimeError("无法到达列表页: %s" % app_current(d))
    # 切到"职位"tab，确保推荐列表可见（App 可能停在消息/我的等 tab）
    try:
        d(text="职位").click()
        time.sleep(2)
    except Exception:
        pass


def back_to_list(d, max_back=3):
    """从详情页返回列表页"""
    for _ in range(max_back):
        d.press("back")
        time.sleep(C.BACK_WAIT)
        if C.MAIN_ACT in current_activity(d):
            return True
    return False


# ---------- 列表页 ----------

def read_cards(d):
    """返回可见卡片列表 [(title, city, salary, cx, cy)]"""
    cards = d(resourceId="com.hpbr.bosszhipin:id/boss_job_card_view")
    out = []
    for i in range(cards.count):
        c = cards[i]
        t = c.child(resourceId="com.hpbr.bosszhipin:id/tv_position_name")
        ct = c.child(resourceId="com.hpbr.bosszhipin:id/tv_distance")
        s = c.child(resourceId="com.hpbr.bosszhipin:id/tv_salary_statue")
        if not t.exists:
            continue
        title = t.info["text"].strip()
        city = ct.info["text"].strip() if ct.exists else ""
        salary = s.info["text"].strip() if s.exists else ""
        b = c.info["bounds"]
        out.append((title, city, salary,
                    (b["left"] + b["right"]) // 2,
                    (b["top"] + b["bottom"]) // 2))
    return out


def swipe_up(d):
    """列表页上滑加载下一屏"""
    x0, y0, x1, y1 = C.LIST_SWIPE
    d.swipe(x0, y0, x1, y1, duration=0.4)
    import random
    time.sleep(random.uniform(*C.SWIPE_PAUSE))


# ---------- 详情页 ----------

def read_detail_header(d):
    """详情页读标题/城市/经验要求"""
    t = d(resourceId="com.hpbr.bosszhipin:id/tv_job_name")
    c = d(resourceId="com.hpbr.bosszhipin:id/tv_required_location")
    e = d(resourceId="com.hpbr.bosszhipin:id/tv_required_work_exp")
    return (t.info["text"].strip() if t.exists else "?",
            c.info["text"].strip() if c.exists else "?",
            e.info["text"].strip() if e.exists else "")


def click_view_more(d):
    """像素定位 tv_description 内青色"查看更多"链接并点击"""
    desc = d(resourceId="com.hpbr.bosszhipin:id/tv_description")
    if not desc.exists:
        return False
    b = desc.info["bounds"]
    png = d.screenshot()
    clusters = teal_clusters(png, b["left"], b["top"], b["right"], b["bottom"])
    cand = [c for c in clusters if (c[1] - c[0]) < 60 and 80 < (c[3] - c[2]) < 300]
    if not cand:
        return False
    c = max(cand, key=lambda c: c[0])  # 最靠下的青色短文本行
    d.click((c[2] + c[3]) // 2, (c[0] + c[1]) // 2)
    return True


def read_full_jd(d):
    """详情页读完整 JD：下滑使 JD 可见，必要时点"查看更多"展开"""
    x0, y0, x1, y1 = C.JD_SWIPE
    d.swipe(x0, y0, x1, y1, duration=0.3)
    time.sleep(1.5)
    desc = d(resourceId="com.hpbr.bosszhipin:id/tv_description")
    if not desc.exists:
        return ""
    text = desc.info["text"]
    if "查看更多" in text:
        if click_view_more(d):
            time.sleep(2)
            desc = d(resourceId="com.hpbr.bosszhipin:id/tv_description")
            if desc.exists:
                text = desc.info["text"]
    return text.replace("&#10;", "\n")


def find_chat_btn(d):
    """返回打招呼按钮（rid 定位；文本随状态在'立即沟通'/'继续沟通'间变化）"""
    for rid in ("btn_chat", "btn_youxuan"):
        b = d(resourceId="com.hpbr.bosszhipin:id/" + rid)
        if b.exists:
            return b
    return None


# ---------- 匹配 ----------

def pre_filter(title, city, exp, salary=""):
    """前置过滤：排除词 + 城市 + 届别 + 经验 + 薪资。

    返回 (passed, reason)：通过时 (True, None)；跳过时 (False, 细分原因)。
    原因取值：pre-skip-word / pre-job-type / pre-city / pre-grad-year /
    pre-exp / pre-salary（供统计模块落盘，判断逻辑与旧版一致）。

    目标画像：27 届应届生。校招/应届、实习、经验 1 年以内都可投；
    其他届别（26届/25届/26秋招/2026校园招聘）、要求 1 年以上经验的跳过；
    "经验不限"岗位若月薪上限超过 MAX_SALARY_K 也跳过（超出应届水平）。
    """
    if any(w in title for w in C.SKIP_WORDS):
        return False, "pre-skip-word"
    if any(w in title for w in C.SKIP_JOB_TYPES):
        return False, "pre-job-type"
    if not any(ct in city for ct in C.CITIES):
        return False, "pre-city"
    # 届别：标题带届/秋招/校园招聘年份时，只认 27 届（2027）
    m = re.search(r"(\d{2})届|(\d{2})秋招|(20\d{2})校园招聘", title)
    if m:
        years = [g for g in m.groups() if g]
        if not any(y in (str(C.GRAD_YEAR), str(2000 + C.GRAD_YEAR)) for y in years):
            return False, "pre-grad-year"
    # 经验：要求 1 年以上（1-3年 / 3-5年 / 5年以上 …）跳过
    if re.search(r"\d+\s*[-~～]\s*\d+\s*年|\d+\s*年以上", exp):
        return False, "pre-exp"
    # 在校/应届、经验不限、1年以内 都接受
    # 薪资：仅"经验不限"岗位按月薪上限判断
    if "不限" in exp and salary:
        sm = re.search(r"(\d+(?:\.\d+)?)\s*[-~～]\s*(\d+(?:\.\d+)?)\s*[Kk千]", salary)
        if sm and float(sm.group(2)) > C.MAX_SALARY_K:
            return False, "pre-salary"
    return True, None


def jd_missing_skill(jd_text):
    """检查 JD 任职要求是否包含我缺失的硬技能，返回技能名或 None"""
    if not jd_text:
        return None
    idx = jd_text.find("任职要求")
    req = jd_text[idx:] if idx >= 0 else jd_text
    req_lower = req.lower()
    for pattern, name in C.MISSING_HARD_SKILLS:
        if re.search(pattern, req_lower):
            return name
    return None


def teal_clusters(img, x0, y0, x1, y1, row_gap=8):
    """区域内按行聚类青色像素，返回 [(ytop,ybot,xleft,xright,count)]"""
    img = img.convert("RGB")
    px = img.load()
    rows = {}
    for y in range(max(0, y0), min(img.height, y1)):
        cnt = 0
        xmin, xmax = 10 ** 9, -1
        for x in range(max(0, x0), min(img.width, x1)):
            r, g, b = px[x, y]
            if g > 150 and b > 140 and r < 120 and abs(g - b) < 60:
                cnt += 1
                xmin = min(xmin, x)
                xmax = max(xmax, x)
        if cnt >= 3:
            rows[y] = (xmin, xmax, cnt)
    if not rows:
        return []
    ys = sorted(rows)
    clusters, cur = [], [ys[0]]
    for prev, y in zip(ys, ys[1:]):
        if y - prev <= row_gap:
            cur.append(y)
        else:
            clusters.append(cur)
            cur = [y]
    clusters.append(cur)
    out = []
    for c in clusters:
        ytop, ybot = c[0], c[-1]
        xs = [rows[y][0] for y in c] + [rows[y][1] for y in c]
        cnt = sum(rows[y][2] for y in c)
        out.append((ytop, ybot, min(xs), max(xs), cnt))
    return out
