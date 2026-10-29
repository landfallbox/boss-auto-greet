# boss-auto-greet

通过 ADB 连接真机，自动在 BOSS 直聘（双开版）推荐流里打招呼。

## 工作原理

用 `uiautomator2`（底层走 ADB）驱动 Android 真机，自动完成：

```
列表页 -> 点卡片 -> 详情页
  -> 前置过滤（城市 / 经验 / 排除词）
  -> 下滑读完整 JD（自动点"查看更多"展开）
  -> JD 硬技能匹配（任职要求含我缺失的硬技能则跳过）
  -> 匹配则点打招呼按钮（自动发默认消息）-> 返回
  -> 一屏点完上滑加载 -> 循环
```

达到当日随机目标（默认 100-120）或连续多屏无新卡片后停止。
已打招呼的岗位记入 `state.json`，当天不重复。

## 环境准备

1. **ADB**：手机开启 USB 调试，数据线连接，`adb devices` 能看到设备。
2. **Python 依赖**：
   ```powershell
   pip install -r requirements.txt
   ```
3. **双开版 BOSS 直聘**：脚本默认驱动小米 XSpace 手机分身里的 BOSS（user 999）。
   单开版 / 其他机型见下方"改配置"。

## 运行

```powershell
# 全自动（达到当日目标后停止）
python -u boss_auto.py

# 空跑：只读卡片+去重，不点详情、不打招呼（用来确认设备/页面正常）
python -u boss_auto.py --dry

# 流程验证：只跑 6 张卡，确认操作链路
python -u verify_flow.py
```

> 用 `-u` 关闭输出缓冲，实时看到日志。

## 改配置

所有可调参数集中在 [config.py](config.py)：

| 参数 | 说明 |
|------|------|
| `SERIAL` | 手机序列号（`adb devices` 查看） |
| `USER` / `LAUNCH_ACT` | 双开用户号与启动 Activity（单开版改 0） |
| `CITIES` | 只投递的城市 |
| `SKIP_WORDS` | 标题含这些词直接跳过（校招/实习/应届等） |
| `MISSING_HARD_SKILLS` | 我缺失的硬技能，JD 任职要求含则跳过 |
| `DAILY_MIN` / `DAILY_MAX` | 每日随机打招呼目标区间 |
| `MAX_EMPTY_SCANS` | 连续几屏无新卡片则停止 |
| `*_SWIPE` | 滑动坐标（1080x2400 分辨率） |

## 文件结构

| 文件 | 作用 |
|------|------|
| [config.py](config.py) | 全部可调参数 |
| [bosslib.py](bosslib.py) | 共享设备操作（读卡片/读JD/匹配/按钮定位） |
| [boss_auto.py](boss_auto.py) | 全自动主入口（状态+目标+循环） |
| [verify_flow.py](verify_flow.py) | 流程验证入口（少量卡片） |
| [statslib.py](statslib.py) | 统计记录 + HTML 日报/半周总结生成 |
| `state.json` | 运行状态（自动生成，已 gitignore） |
| `stats/` | 每日统计 JSON：投递/跳过明细（自动生成，已 gitignore） |
| `reports/` | HTML 日报 + 半周总结 + 跨天总览（自动生成，已 gitignore） |

## 注意

- 跑完（含中途中断）自动在 `reports/` 生成当天 HTML 日报，浏览器直接打开；周二/周五跑完额外生成半周总结。
- `reports/overview.html` 为跨天总览（汇总卡片 + 逐日投递趋势 + 每日明细表），每次跑完自动刷新，日报页头部可跳转。
- 打招呼用 App 默认消息，不发送自定义内容。
- 按钮文本会随状态变化：未打过显示"立即沟通"（计入），已打过显示"继续沟通"（不计入）。
- 频繁自动化可能触发平台风控，建议控制每日数量、保持账号正常活跃。
