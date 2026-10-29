# -*- coding: utf-8 -*-
"""BOSS 直聘自动打招呼（真机双开版，全自动）——主入口。

流程：
  1. 确保双开版 BOSS 在职位推荐列表页
  2. 循环：读可见卡片 -> 城市/经验前置过滤 -> 去重
  3. 通过过滤：点卡片 -> 详情页 -> 下滑读完整 JD -> JD 硬技能匹配
  4. 匹配：点打招呼按钮 -> 返回；不匹配：直接返回
  5. 一屏点完 -> 上滑加载 -> 继续
  6. 达到当日随机目标或连续多屏无新增后停止

匹配规则、设备、城市、目标数等全部在 config.py 配置。
设备操作函数在 bosslib.py。
投递/跳过明细落盘 stats/，跑完自动生成 HTML 日报 reports/（周二/周五另有半周总结）。

运行：
  python -u boss_auto.py          # 全自动
  python -u boss_auto.py --dry    # 空跑（只读卡片+去重，不点详情/不打招呼）
"""
import json
import os
import random
import time

import bosslib as bl
import config as C
import statslib

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")


# ---------- 状态 ----------

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(st):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False)


def main():
    import sys
    dry = "--dry" in sys.argv

    st = load_state()
    today = time.strftime("%Y-%m-%d")
    if st.get("date") != today:
        st = {"date": today, "sent": 0, "seen": []}
        save_state(st)

    target = random.randint(C.DAILY_MIN, C.DAILY_MAX)
    print("today=%s sent=%d target=%d" % (today, st["sent"], target))
    if st["sent"] >= target:
        print("already reached target, nothing to do")
        if not dry:
            statslib.finish()
        return
    if not dry:
        statslib.set_target(target)

    d = bl.connect()
    try:
        bl.ensure_list_page(d)

        seen = set(st["seen"])
        empty_scans = 0
        sent_now = 0

        while st["sent"] < target and empty_scans < C.MAX_EMPTY_SCANS:
            cards = bl.read_cards(d)
            new_cards = [(t, c, s, x, y) for (t, c, s, x, y) in cards if (t, c) not in seen]
            if not new_cards:
                bl.swipe_up(d)
                empty_scans += 1
                continue
            empty_scans = 0

            if dry:
                for title, city, salary, cx, cy in new_cards:
                    seen.add((title, city))
                save_state(st)
                bl.swipe_up(d)
                continue

            for title, city, salary, cx, cy in new_cards:
                if st["sent"] >= target:
                    break
                seen.add((title, city))

                # 点卡片进详情（最多试 2 次）
                d.click(cx, cy)
                time.sleep(C.DETAIL_WAIT)
                act = bl.current_activity(d)
                if C.DETAIL_ACT not in act:
                    d.click(cx, cy)
                    time.sleep(C.DETAIL_WAIT)
                    act = bl.current_activity(d)
                    if C.DETAIL_ACT not in act:
                        print("skip(no detail): %s" % title)
                        statslib.record("skipped", {"title": title, "city": city,
                                                    "salary": salary,
                                                    "reason": "no-detail"})
                        continue

                # 详情页头信息 + 前置过滤
                d_title, d_city, d_exp = bl.read_detail_header(d)
                passed, pre_reason = bl.pre_filter(d_title, d_city, d_exp, salary)
                if not passed:
                    print("skip(pre): %s | %s | %s" % (d_title, d_city, d_exp))
                    statslib.record("skipped", {"title": d_title, "city": d_city,
                                                "salary": salary, "exp": d_exp,
                                                "reason": pre_reason})
                    bl.back_to_list(d)
                    continue

                # 读完整 JD + 硬技能匹配
                jd = bl.read_full_jd(d)
                miss = bl.jd_missing_skill(jd)
                if miss:
                    print("skip(jd-%s): %s" % (miss, d_title))
                    statslib.record("skipped", {"title": d_title, "city": d_city,
                                                "salary": salary, "exp": d_exp,
                                                "jd": jd,
                                                "reason": "jd-skill:" + miss})
                    bl.back_to_list(d)
                    continue

                # 点打招呼按钮（rid 定位；文本区分新打招呼/继续沟通）
                btn = bl.find_chat_btn(d)
                if not btn:
                    print("skip(no btn): %s" % d_title)
                    statslib.record("skipped", {"title": d_title, "city": d_city,
                                                "salary": salary, "exp": d_exp,
                                                "jd": jd,
                                                "reason": "no-btn"})
                    bl.back_to_list(d)
                    continue
                btn_text = btn.info["text"]
                btn.click()
                time.sleep(4)
                act = bl.current_activity(d)
                if C.CHAT_ACT in act:
                    if "立即沟通" in btn_text:
                        st["sent"] += 1
                        sent_now += 1
                        print("sent %d/%d: %s | %s" % (st["sent"], target, d_title, d_city))
                        statslib.record("sent", {"title": d_title, "city": d_city,
                                                 "salary": salary, "exp": d_exp,
                                                 "jd": jd})
                    else:
                        print("resume-chat(不计): %s | %s" % (d_title, d_city))
                        statslib.record("resumed", {"title": d_title, "city": d_city,
                                                    "salary": salary, "exp": d_exp,
                                                    "jd": jd})
                else:
                    print("chat-fail: %s | %s -> %s" % (d_title, d_city, act))
                    statslib.record("skipped", {"title": d_title, "city": d_city,
                                                "salary": salary, "exp": d_exp,
                                                "jd": jd, "fail_act": act,
                                                "reason": "chat-fail"})
                bl.back_to_list(d)

            save_state(st)
            bl.swipe_up(d)

        save_state(st)
        print("done. sent_now=%d total=%d target=%d empty_scans=%d"
              % (sent_now, st["sent"], target, empty_scans))
    finally:
        if not dry:
            statslib.finish()


if __name__ == "__main__":
    main()
