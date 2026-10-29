# -*- coding: utf-8 -*-
"""主流程验证（不验证数量上限）——验证入口。

跑少量卡片（MAX_CARDS），确认操作链路：
  进主页 -> 点卡片 -> 详情页 -> 前置过滤 -> 读完整 JD -> 硬技能匹配
  -> 匹配则打招呼 -> 返回 -> 一屏点完往下翻 -> 重复

参数同样来自 config.py，设备操作来自 bosslib.py。
运行：
  python -u verify_flow.py
"""
import time

import bosslib as bl
import config as C

MAX_CARDS = 6  # 本次验证最多处理几张卡


def main():
    d = bl.connect()
    ok = _ensure_main(d)
    print("step1 进主页:", "OK" if ok else "FAIL")
    if not ok:
        print("当前页:", bl.current_activity(d))
        return

    processed = 0
    sent = 0
    skipped = 0

    while processed < MAX_CARDS:
        cards = d(resourceId="com.hpbr.bosszhipin:id/boss_job_card_view")
        n = cards.count
        print("屏上卡片数:", n)
        if n == 0:
            print("无卡片，往下翻一屏")
            bl.swipe_up(d)
            continue

        take = min(n, MAX_CARDS - processed)
        for i in range(take):
            if processed >= MAX_CARDS:
                break
            c = cards[i]
            t = c.child(resourceId="com.hpbr.bosszhipin:id/tv_position_name")
            if not t.exists:
                continue
            card_title = t.info["text"].strip()
            sc = c.child(resourceId="com.hpbr.bosszhipin:id/tv_salary_statue")
            card_salary = sc.info["text"].strip() if sc.exists else ""

            # 点卡片进详情（最多试 2 次）
            entered = False
            for _ in range(2):
                t.click()
                time.sleep(C.DETAIL_WAIT)
                if C.DETAIL_ACT in bl.current_activity(d):
                    entered = True
                    break
            if not entered:
                print("[%d] 未进详情，跳过: %s" % (i, card_title))
                continue

            title, city, exp = bl.read_detail_header(d)
            if not bl.pre_filter(title, city, exp, card_salary):
                print("[%d] 前置不匹配: %s | %s | %s" % (i, title, city, exp))
                skipped += 1
                bl.back_to_list(d)
                processed += 1
                time.sleep(1)
                continue

            jd = bl.read_full_jd(d)
            miss = bl.jd_missing_skill(jd)
            if miss:
                print("[%d] JD不匹配(%s): %s" % (i, miss, title))
                skipped += 1
                bl.back_to_list(d)
                processed += 1
                time.sleep(1)
                continue

            print("[%d] 匹配: %s | %s | JD%d字" % (i, title, city, len(jd)))
            btn = bl.find_chat_btn(d)
            if btn:
                btn_text = btn.info["text"]
                btn.click()
                time.sleep(4)
                if C.CHAT_ACT in bl.current_activity(d):
                    if "立即沟通" in btn_text:
                        sent += 1
                        print("[%d] 打招呼成功" % i)
                    else:
                        print("[%d] 继续沟通(已有会话,不计)" % i)
                else:
                    print("[%d] 打招呼失败，页面: %s" % (i, bl.current_activity(d)))
            else:
                print("[%d] 无打招呼按钮" % i)

            if not bl.back_to_list(d):
                print("返回主页失败，当前页: %s" % bl.current_activity(d))
                return
            processed += 1
            time.sleep(1)

        if processed >= MAX_CARDS:
            break
        print("一屏处理完，往下翻一屏")
        bl.swipe_up(d)

    print("验证完成: 处理%d 打招呼%d 跳过%d" % (processed, sent, skipped))


def _ensure_main(d):
    """确保在列表页（薄封装，复用 bosslib.ensure_list_page 的返回语义）"""
    try:
        bl.ensure_list_page(d)
    except RuntimeError:
        return False
    return C.MAIN_ACT in bl.current_activity(d)


if __name__ == "__main__":
    main()
