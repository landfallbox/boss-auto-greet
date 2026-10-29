# -*- coding: utf-8 -*-
"""boss-auto-greet 全部可调参数。

换手机 / 改城市 / 调数量 / 调技能词，只改这里，不用动主脚本。
"""

# ---------- 设备 ----------
# adb devices 里看到的序列号（数据线连接的真机）
SERIAL = "75798daf"

# ---------- BOSS 直聘 App（双开版） ----------
PKG = "com.hpbr.bosszhipin"
# XSpace 双开的用户号（小米"手机分身"）。
# 若用单开版 BOSS，把 USER 改成 0，LAUNCH_ACT 用默认启动即可。
USER = 999
LAUNCH_ACT = "com.hpbr.bosszhipin.module.launcher.WelcomeActivity"

# 关键 Activity（用子串匹配，注意点号前缀）
MAIN_ACT = "module.main.activity.MainActivity"      # 职位推荐列表页
DETAIL_ACT = "BossJobPagerActivity"                 # 职位详情页
CHAT_ACT = "ChatRoomActivity"                       # 聊天页

# ---------- 匹配：前置过滤 ----------
# 我是 27 届应届生：校招/实习/应届岗位都是目标
# 标题带其他届别/秋招年份（26届、25届、26秋招、2026校园招聘…）直接跳过
GRAD_YEAR = 27

# 经验要求：在校/应届、经验不限、1年以内 可投；1-3年及以上跳过
# "经验不限" 岗位若月薪上限超过 MAX_SALARY_K 则跳过（超出应届水平）
MAX_SALARY_K = 30

# 只在这些城市投递
CITIES = ["上海", "苏州", "南京", "泰州", "无锡", "常州", "杭州"]

# 标题含这些词直接跳过（当前为空，可按需加，如 "兼职"）
SKIP_WORDS = []

# 非技术岗黑名单：标题含这些词直接跳过（用户是研发/AI 方向，不投这些）
SKIP_JOB_TYPES = [
    "客服", "销售", "管培", "运营", "行政", "顾问", "管家",
    "视频", "主播", "剪辑", "文案", "翻译", "编辑",
    "财务", "会计", "人事", "招聘", "市场", "商务",
    "电话", "电销", "设计",
    "储备", "规划师", "档案", "专员", "经理", "优才", "菁英", "专岗",
]

# ---------- 匹配：JD 硬技能 ----------
# 我具备的技能（参考用；当前匹配主要靠下面的缺失硬技能排除）
USER_SKILLS = [
    "java", "python", "全栈", "spring", "mysql", "linux", "git",
    "ai agent", "大模型", "llm", "rag", "模型部署", "plm", "coding",
    "后端", "前端", "web", "api", "docker", "微服务", "redis", "kafka",
]

# 我完全没有的硬技能：JD"任职要求"里出现 -> 判定不匹配（跳过）
# 每项是 (正则, 名称)。正则按小写匹配。
MISSING_HARD_SKILLS = [
    (r"c\+\+", "C++"),
    (r"ros2?\b", "ROS"),
    (r"opencv", "OpenCV"),
    (r"\bpcl\b", "PCL"),
    (r"嵌入式", "嵌入式"),
    (r"单片机", "单片机"),
    (r"fpga", "FPGA"),
    (r"硬件开发|硬件工程师", "硬件"),
    (r"cuda", "CUDA"),
    (r"汇编", "汇编"),
    (r"\brust\b|\bgolang\b|go语言", "Rust/Go"),
    (r"c#|csharp", "C#"),
    (r"unity|unreal", "游戏引擎"),
    (r"图形学", "图形学"),
    (r"量化", "量化"),
    (r"区块链", "区块链"),
]

# ---------- 运行参数 ----------
# 每日随机打招呼目标区间
DAILY_MIN, DAILY_MAX = 100, 120

# 连续 N 屏读不到新卡片 -> 停止（推荐流到底了）
MAX_EMPTY_SCANS = 4

# 时序（秒）
DETAIL_WAIT = 5        # 点卡片后等详情页加载
BACK_WAIT = 2          # 每次返回后等待
SWIPE_PAUSE = (2.5, 4.5)  # 上滑加载后随机等待区间

# ---------- 屏幕坐标（1080x2400 分辨率） ----------
# 详情页下滑（让 JD 可见 / 展开）
JD_SWIPE = (540, 1700, 540, 900)
# 列表页上滑（加载下一屏）
LIST_SWIPE = (540, 1800, 540, 800)
