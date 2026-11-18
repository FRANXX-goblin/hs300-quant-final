"""End-to-end research pipeline.

Run from the project root:

    python scripts/run_all.py
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import config
from src import analysis, attribution, backtest, charts, data, factors, portfolio, report_docx, risk


def _fmt(x):
    return None if pd.isna(x) else float(x)


def main():
    print("[1/9] 载入数据 ...")
    bench = data.load_benchmark()
    calendar = bench["date"].tolist()
    hist = data.load_constituents()
    cur = pd.read_parquet(config.DATA_DIR / "constituents_current_2026.parquet")
    codes = sorted(set(hist["code"]) | set(cur["code"]))
    stock_data = data.load_stock_data(codes)
    industry = data.load_industry()

    signal_dates = data.month_end_dates(calendar, config.BACKTEST_START, config.SIGNAL_END)
    cons_by_date = data.constituents_by_date(signal_dates)
    print(f"    股票数 {len(stock_data)}，调仓期数 {len(signal_dates)}，"
          f"{signal_dates[0].date()} ~ {signal_dates[-1].date()}")

    panel_path = config.TABLE_DIR / "panel.parquet"
    if panel_path.exists():
        panel = pd.read_parquet(panel_path)
    else:
        panel = factors.build_monthly_panel(
            stock_data, signal_dates, cons_by_date,
            bench.set_index("date")["ret"], industry)
        panel.to_parquet(panel_path, index=False)
    print(f"    月度面板 {panel.shape}")

    panels = data.build_panels(stock_data, calendar)
    ret_panel = panels["ret"]
    amount_panel = panels["amount"]

    pairs_bt = data.execution_pairs(
        calendar, [d for d in signal_dates if d <= pd.Timestamp(config.BACKTEST_END)],
        config.BACKTEST_END)
    pairs_2026 = data.execution_pairs(
        calendar, [d for d in signal_dates if d >= pd.Timestamp("2025-12-01")],
        config.LIVE_END)
    print(f"    回测期数 {len(pairs_bt)}，2026样本外期数 {len(pairs_2026)}")

    print("[2/9] 因子有效性检验 ...")
    # 用 2018-2025 做因子检验，2026 单列
    panel_bt = panel[panel["date"] <= pd.Timestamp(config.BACKTEST_END)]
    ana_bt = analysis.save_analysis(panel_bt)
    print(ana_bt["ic_summary"][ana_bt["ic_summary"]["period"] == "全样本"]
          [["name", "mean_ic", "icir", "t_stat"]].round(3).to_string(index=False))

    print("[3/9] 回测基准模型与研究模型 ...")
    backtests = {}
    for model in ["baseline", "research"]:
        sel, hold = portfolio.select_portfolios(
            panel, pairs_bt, model=model, industry_cap=config.INDUSTRY_CAP)
        res, turn, hlog = backtest.run_backtest(
            calendar, pairs_bt, sel, ret_panel, bench, config.BACKTEST_END)
        m, dd = backtest.calc_metrics(res)
        backtests[model] = {
            "selection": sel, "holdings": hold, "result": res,
            "turnover": turn, "holdings_log": hlog, "metrics": m, "dd": dd,
        }
        print(f"    {model}: 年化 {m['年化收益']*100:.2f}%  "
              f"夏普 {m['夏普比率']:.3f}  最大回撤 {m['最大回撤']*100:.2f}%  "
              f"超额 {m['年化超额收益']*100:.2f}%")

    print("[4/9] 产品实施版（单一行业≤10只）...")
    sel_p, hold_p = portfolio.select_portfolios(
        panel, pairs_bt, model="research", industry_cap=10)
    res_p, turn_p, hlog_p = backtest.run_backtest(
        calendar, pairs_bt, sel_p, ret_panel, bench, config.BACKTEST_END)
    m_p, dd_p = backtest.calc_metrics(res_p)
    print(f"    产品版: 年化 {m_p['年化收益']*100:.2f}%  "
          f"夏普 {m_p['夏普比率']:.3f}  最大回撤 {m_p['最大回撤']*100:.2f}%")

    # ---------- 指标表 ----------
    base_m = backtests["baseline"]["metrics"]
    res_m = backtests["research"]["metrics"]
    metric_rows = [
        {"组合": "基准模型（价值+规模）", **base_m,
         "平均单边换手率": backtests["baseline"]["turnover"]["turnover_oneway"].mean(),
         "平均持仓数": backtests["baseline"]["holdings_log"].groupby("exec_date").size().mean()},
        {"组合": "研究模型（+低波+低换手）", **res_m,
         "平均单边换手率": backtests["research"]["turnover"]["turnover_oneway"].mean(),
         "平均持仓数": backtests["research"]["holdings_log"].groupby("exec_date").size().mean()},
        {"组合": "产品实施版（行业≤10只）", **m_p,
         "平均单边换手率": turn_p["turnover_oneway"].mean(),
         "平均持仓数": hlog_p.groupby("exec_date").size().mean()},
    ]
    bm_row = {
        "组合": "沪深300全收益指数",
        "累计收益": res_m["基准累计收益"], "年化收益": res_m["基准年化收益"],
        "年化波动": res_m["基准年化波动"], "夏普比率": res_m["基准夏普比率"],
        "最大回撤": res_m["基准最大回撤"], "卡玛比率": np.nan,
        "基准累计收益": np.nan, "基准年化收益": np.nan, "基准年化波动": np.nan,
        "基准夏普比率": np.nan, "基准最大回撤": np.nan, "年化超额收益": np.nan,
        "跟踪误差": np.nan, "信息比率": np.nan, "Beta": 1.0, "年化Alpha": np.nan,
        "月度胜率": np.nan, "上行捕获率": np.nan, "下行捕获率": np.nan,
        "日VaR95": np.nan, "日CVaR95": np.nan, "月度最佳": np.nan,
        "月度最差": np.nan, "日收益偏度": np.nan, "日收益峰度": np.nan,
        "交易日数": res_m["交易日数"], "平均单边换手率": np.nan, "平均持仓数": np.nan,
    }
    metric_rows.append(bm_row)
    metrics_df = pd.DataFrame(metric_rows).set_index("组合")
    metrics_df.to_csv(config.TABLE_DIR / "metrics.csv", encoding="utf-8-sig")

    # ---------- 年度收益 ----------
    ann_b = backtest.annual_returns(backtests["baseline"]["result"])
    ann_r = backtest.annual_returns(backtests["research"]["result"])
    ann = pd.DataFrame(index=ann_r.index)
    ann["基准模型"] = ann_b["组合"]
    ann["研究模型"] = ann_r["组合"]
    ann["沪深300"] = ann_r["基准"]
    ann["研究超额"] = ann["研究模型"] - ann["沪深300"]
    ann.to_csv(config.TABLE_DIR / "annual_returns.csv", encoding="utf-8-sig")

    dd_table = backtest.drawdown_table(backtests["research"]["result"])
    dd_table.to_csv(config.TABLE_DIR / "drawdown_table.csv", index=False, encoding="utf-8-sig")

    rolling = backtest.rolling_metrics(backtests["research"]["result"])
    rolling.to_csv(config.TABLE_DIR / "rolling_metrics.csv", encoding="utf-8-sig")

    stress = backtest.stress_periods(backtests["research"]["result"], risk.STRESS_PERIODS)
    stress.to_csv(config.TABLE_DIR / "stress.csv", index=False, encoding="utf-8-sig")

    # ---------- 归因 ----------
    print("[5/9] 收益归因与风险分析 ...")
    hold_r = backtests["research"]["holdings"]
    turn_r = backtests["research"]["turnover"]
    fr, fs, resid = attribution.fama_macbeth(panel_bt)
    fs.to_csv(config.TABLE_DIR / "attribution_factor_premia.csv", index=False, encoding="utf-8-sig")
    fr.to_csv(config.TABLE_DIR / "attribution_factor_returns.csv", encoding="utf-8-sig")
    attr = attribution.portfolio_attribution(
        panel_bt, hold_r, fr,
        cost_by_signal=dict(zip(turn_r["signal_date"], turn_r["cost"])))
    attr.to_csv(config.TABLE_DIR / "attribution_detail.csv", encoding="utf-8-sig")
    attr_sum = attribution.attribution_summary(attr)
    attr_sum.to_csv(config.TABLE_DIR / "attribution_summary.csv", index=False, encoding="utf-8-sig")

    style = attribution.style_exposure(panel_bt, hold_r)
    style.to_csv(config.TABLE_DIR / "style_exposure.csv", encoding="utf-8-sig")
    ind_detail = attribution.industry_exposure(panel_bt, hold_r)
    ind_detail.to_csv(config.TABLE_DIR / "industry_exposure_detail.csv", index=False, encoding="utf-8-sig")
    ind_avg = ind_detail.groupby("industry")["active"].mean().sort_values()
    ind_avg.to_csv(config.TABLE_DIR / "industry_active_avg.csv", encoding="utf-8-sig")
    risk_dec = attribution.risk_decomposition(attr, fr)
    risk_dec.to_csv(config.TABLE_DIR / "risk_decomposition.csv", index=False, encoding="utf-8-sig")

    # ---------- 产品分析 ----------
    print("[6/9] 容量与费率分析 ...")
    cap = risk.capacity_analysis(hold_p, amount_panel)
    cap.to_csv(config.TABLE_DIR / "capacity.csv", index=False, encoding="utf-8-sig")
    fee = risk.fee_scenarios(m_p["年化收益"], m_p["基准年化收益"], m_p["年化波动"])
    fee.to_csv(config.TABLE_DIR / "fee.csv", index=False, encoding="utf-8-sig")

    # 参数敏感性
    sens_rows = []
    for top in [20, 30, 40, 50]:
        for cost in [0.0005, 0.0010, 0.0015, 0.0020]:
            sel, _ = portfolio.select_portfolios(panel, pairs_bt, model="research", top_n=top)
            res, turn, _ = backtest.run_backtest(
                calendar, pairs_bt, sel, ret_panel, bench, config.BACKTEST_END,
                cost_rate=cost)
            m, _ = backtest.calc_metrics(res)
            sens_rows.append({"top_n": top, "cost": cost,
                              "annual": m["年化收益"], "sharpe": m["夏普比率"],
                              "mdd": m["最大回撤"], "ir": m["信息比率"],
                              "turnover": turn["turnover_oneway"].mean()})
    sens = pd.DataFrame(sens_rows)
    sens.to_csv(config.TABLE_DIR / "sensitivity.csv", index=False, encoding="utf-8-sig")

    # ---------- 2026 样本外 ----------
    print("[7/9] 2026 年样本外模拟 ...")
    oos = {}
    for model, cap_n in [("baseline", None), ("research", None), ("research", 10)]:
        key = f"{model}_{'cap10' if cap_n else 'free'}"
        sel, hold = portfolio.select_portfolios(
            panel, pairs_2026, model=model, industry_cap=cap_n)
        res, turn, hlog = backtest.run_backtest(
            calendar, pairs_2026, sel, ret_panel, bench, config.LIVE_END)
        m, _ = backtest.calc_metrics(res)
        oos[key] = {"result": res, "metrics": m, "holdings": hold,
                    "turnover": turn}
    oos_rows = []
    for k, v in oos.items():
        m = v["metrics"]
        oos_rows.append({"组合": k, "年化收益": m["年化收益"], "年化波动": m["年化波动"],
                         "夏普比率": m["夏普比率"], "最大回撤": m["最大回撤"],
                         "年化超额收益": m["年化超额收益"], "信息比率": m["信息比率"],
                         "Beta": m["Beta"], "月度胜率": m["月度胜率"]})
    pd.DataFrame(oos_rows).set_index("组合").to_csv(
        config.TABLE_DIR / "metrics_2026.csv", encoding="utf-8-sig")
    oos["research_free"]["result"][["nav", "bm_nav", "ret", "bm_ret"]].to_csv(
        config.TABLE_DIR / "nav_2026.csv", encoding="utf-8-sig")

    # ---------- 实盘信号 ----------
    last_signal = signal_dates[-1]
    live_pair = data.execution_pairs(calendar, [last_signal], config.LIVE_END)
    if live_pair:
        sel_live, hold_live = portfolio.select_portfolios(
            panel, live_pair, model="research", industry_cap=10)
        raw_map = pd.read_parquet(config.DATA_DIR / "industry_map.parquet")
        num = raw_map["code"].astype(str).str.zfill(6)
        market = np.where(num.str.startswith("6"), "sh", "sz")
        raw_map["code_full"] = [f"{m}.{n}" for m, n in zip(market, num)]
        name_map = raw_map.set_index("code_full")["name"]
        hold_live["name"] = hold_live["code"].map(name_map).fillna("")
        hold_live["code6"] = hold_live["code"].str.split(".").str[1]
        hold_live.to_csv(config.LIVE_DIR / "holdings_latest.csv",
                         index=False, encoding="utf-8-sig")
        backtests["research"]["holdings"].to_csv(
            config.TABLE_DIR / "holdings_research.csv", index=False, encoding="utf-8-sig")
        hold_p.to_csv(config.TABLE_DIR / "holdings_product.csv", index=False, encoding="utf-8-sig")
        print(f"    最新信号 {last_signal.date()}，执行 {live_pair[0][1].date()}，"
              f"持仓 {len(hold_live)} 只")
    else:
        hold_live = pd.DataFrame()

    # ---------- 图表 ----------
    print("[8/9] 生成图表 ...")
    bench_res = pd.DataFrame(index=backtests["research"]["result"].index)
    bench_res["nav"] = backtests["research"]["result"]["bm_nav"]
    charts.plot_nav({
        "研究模型": backtests["research"]["result"],
        "基准模型": backtests["baseline"]["result"],
        "沪深300": bench_res,
    })
    charts.plot_drawdown({
        "研究模型": backtests["research"]["result"],
        "基准模型": backtests["baseline"]["result"],
        "沪深300": bench_res,
    })
    charts.plot_annual(ann)
    charts.plot_ic_bar(ana_bt["ic_summary"])
    charts.plot_ic_heatmap(ana_bt["ic_by_year"])
    charts.plot_quantiles(ana_bt["quantiles"])
    charts.plot_corr(ana_bt["correlation"])
    charts.plot_exposure(style)
    charts.plot_attribution(attr)
    charts.plot_rolling(rolling)
    charts.plot_stress(stress)
    charts.plot_capacity(cap)
    charts.plot_fee(fee)
    charts.plot_industry(ind_avg)
    charts.plot_turnover(turn_r)
    charts.plot_sensitivity(sens)
    charts.plot_live(oos["research_free"]["result"])

    # ---------- 保存关键配置 ----------
    info = {
        "sample_start": str(signal_dates[0].date()),
        "sample_end": str(signal_dates[-1].date()),
        "n_periods": len(signal_dates),
        "n_stocks": len(stock_data),
        "n_holdings": int(backtests["research"]["holdings_log"].groupby("exec_date").size().mean()),
        "avg_turnover": float(turn_r["turnover_oneway"].mean()),
        "metrics_research": {k: _fmt(v) for k, v in res_m.items()},
        "metrics_baseline": {k: _fmt(v) for k, v in base_m.items()},
        "metrics_product": {k: _fmt(v) for k, v in m_p.items()},
        "metrics_2026": {k: {kk: _fmt(vv) for kk, vv in v["metrics"].items()}
                         for k, v in oos.items()},
    }
    with open(config.TABLE_DIR / "info.json", "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    # ---------- 报告 ----------
    print("[9/9] 生成 Word 技术报告 ...")
    report_docx.build_report()
    print("完成。输出目录：", config.OUTPUT_DIR)


if __name__ == "__main__":
    main()
