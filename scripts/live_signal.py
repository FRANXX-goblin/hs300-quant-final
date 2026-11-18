"""Generate the latest live signal for the Xueqiu model portfolio."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from src import data, factors, portfolio


def main():
    bench = data.load_benchmark()
    calendar = bench["date"].tolist()
    hist = data.load_constituents()
    cur = pd.read_parquet(config.DATA_DIR / "constituents_current_2026.parquet")
    codes = sorted(set(hist["code"]) | set(cur["code"]))
    stock_data = data.load_stock_data(codes)
    industry = data.load_industry()

    signal_dates = data.month_end_dates(calendar, config.BACKTEST_START, config.SIGNAL_END)
    last_signal = signal_dates[-1]
    panel_path = config.TABLE_DIR / "panel.parquet"
    rebuild = True
    if panel_path.exists():
        panel = pd.read_parquet(panel_path)
        if len(panel) and panel["date"].max() >= pd.Timestamp(last_signal):
            rebuild = False
    if rebuild:
        cons_by_date = data.constituents_by_date(signal_dates)
        panel = factors.build_monthly_panel(
            stock_data, signal_dates, cons_by_date,
            bench.set_index("date")["ret"], industry)
        panel.to_parquet(panel_path, index=False)
    pairs = data.execution_pairs(calendar, [last_signal], config.LIVE_END)
    if not pairs:
        raise SystemExit("no valid execution date")
    sel, hold = portfolio.select_portfolios(
        panel, pairs, model="research", industry_cap=10)

    raw_map = pd.read_parquet(config.DATA_DIR / "industry_map.parquet")
    num = raw_map["code"].astype(str).str.zfill(6)
    market = np.where(num.str.startswith("6"), "sh", "sz")
    raw_map["code_full"] = [f"{m}.{n}" for m, n in zip(market, num)]
    name_map = raw_map.set_index("code_full")["name"]
    hold["code6"] = hold["code"].str.split(".").str[1]
    fallback = {"688009": "中国通号", "000157": "中联重科"}
    hold["name"] = (hold["code"].map(name_map)
                    .fillna(hold["code6"].map(fallback))
                    .fillna(""))
    hold["weight"] = 1.0 / len(hold)

    out = config.LIVE_DIR / "holdings_latest.csv"
    hold.to_csv(out, index=False, encoding="utf-8-sig")

    sig_date = pd.Timestamp(last_signal).date()
    exec_date = pd.Timestamp(pairs[0][1]).date()
    lines = [
        f"# 雪球模拟组合：{config.PRODUCT_NAME}",
        "",
        f"- 股票池：沪深300历史成分股（2026年冻结2025-11-28名单）",
        f"- 最新信号日：{sig_date}",
        f"- 建议建仓/调仓日：{exec_date}",
        f"- 持仓数量：{len(hold)} 只，等权",
        f"- 业绩基准：{config.BENCHMARK_NAME}",
        "- 调仓规则：每月最后一个交易日生成信号，下一交易日收盘调仓",
        "- 组合链接（创建后替换）：" + config.XUEQIU_LINK,
        "",
        "## 最新持仓",
        "",
        "| 序号 | 代码 | 名称 | 行业 | 权重 | 综合得分 |",
        "| ---: | --- | --- | --- | ---: | ---: |",
    ]
    for _, r in hold.sort_values("rank").iterrows():
        nm = r["name"] if isinstance(r["name"], str) and r["name"] else "—"
        lines.append(
            f"| {int(r['rank'])} | {r['code6']} | {nm} | {r['industry']} | "
            f"{r['weight']*100:.2f}% | {r['score']:.3f} |")
    lines += [
        "",
        "## 雪球创建步骤",
        "",
        "1. 登录雪球网（xueqiu.com），进入“模拟组合”→“创建组合”。",
        f"2. 组合名称填写“{config.PRODUCT_NAME}”，组合类型选择“公开”，基准选择沪深300。",
        f"3. 按上表30只股票等权买入（每只约3.33%），记录建仓日期为 {exec_date}。",
        "4. 每月最后一个交易日收盘后运行 `python scripts/live_signal.py`，",
        "   按新的 `output/live/holdings_latest.csv` 在下一交易日调仓。",
        "5. 将组合链接填入 `config.py` 的 `XUEQIU_LINK`，并更新报告封面。",
        "",
        "> 模拟组合仅用于课程研究与策略跟踪，不构成投资建议。",
    ]
    md = config.LIVE_DIR / "xueqiu_portfolio.md"
    md.write_text("\n".join(lines), encoding="utf-8")
    print("saved:", out)
    print("saved:", md)
    print(hold[["code6", "name", "industry", "weight", "score"]].to_string(index=False))


if __name__ == "__main__":
    main()
