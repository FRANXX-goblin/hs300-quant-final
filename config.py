from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = BASE_DIR / "output"
TABLE_DIR = OUTPUT_DIR / "tables"
FIG_DIR = OUTPUT_DIR / "figures"
REPORT_DIR = OUTPUT_DIR / "report"
LIVE_DIR = OUTPUT_DIR / "live"

for p in (DATA_DIR, CACHE_DIR, OUTPUT_DIR, TABLE_DIR, FIG_DIR, REPORT_DIR, LIVE_DIR):
    p.mkdir(parents=True, exist_ok=True)

DATA_START = "2017-01-01"
BACKTEST_START = "2018-01-01"
BACKTEST_END = "2025-12-31"
LIVE_START = "2026-01-01"
LIVE_END = "2026-11-11"
SIGNAL_END = "2026-10-31"

TRAIN_END = "2021-12-31"
VALID_START = "2022-01-01"

TOP_N = 30
N_QUANTILES = 5
COST_RATE = 0.001
RISK_FREE = 0.02
MIN_HISTORY = 120
INDUSTRY_CAP = None

FACTORS = [
    "ep", "bp", "size", "mom_12_1", "rev_1m", "vol_20", "vol_60",
    "turn_20", "turn_60", "turn_cv_20", "ivol_60", "max_20",
    "beta_60", "amihud_20", "turn_abn", "downvol_60",
]

FACTOR_NAMES = {
    "ep": "盈利收益率(EP)",
    "bp": "账面市值比(BP)",
    "value": "价值(EP+BP)",
    "size": "小市值",
    "mom_12_1": "12-1月动量",
    "rev_1m": "1月反转",
    "vol_20": "低波动(20日)",
    "vol_60": "低波动(60日)",
    "turn_20": "低换手(20日)",
    "turn_60": "低换手(60日)",
    "turn_cv_20": "换手稳定性(20日)",
    "ivol_60": "低特质波动(60日)",
    "max_20": "低极端收益(20日)",
    "beta_60": "低Beta(60日)",
    "amihud_20": "非流动性(20日)",
    "turn_abn": "低异常换手",
    "downvol_60": "低下行波动(60日)",
    "baseline": "基准模型得分",
    "research": "研究模型得分",
}

BASELINE_FACTORS = ["value", "size"]
RESEARCH_FACTORS = ["value", "size", "vol_20", "turn_20"]
ATTRIBUTION_FACTORS = ["value", "size", "vol_20", "turn_20"]

MODEL_NAMES = {
    "baseline": "基准模型（价值+规模）",
    "research": "研究模型（价值+规模+低波20日+低换手20日）",
    "benchmark": "沪深300全收益指数",
}

PRODUCT_NAME = "沪深300低风险增强一号"
PRODUCT_ROLE = "私募证券投资基金（量化多头）"
BENCHMARK_NAME = "沪深300全收益指数（H00300）"

# 请提交前替换为真实信息
MEMBERS = [
    {"name": "李嘉铭", "sid": "2023101386", "role": "模型构建、代码编写、文档编写"},
    {"name": "王硕", "sid": "2023103416", "role": "模型构建、代码编写、文档编写"},
]
GITHUB_LINK = "https://github.com/yourname/hs300-quant-final"
XUEQIU_LINK = "https://xueqiu.com/P/YOUR_PORTFOLIO"
