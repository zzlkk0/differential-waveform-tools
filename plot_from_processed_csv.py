#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 sine_fit_settling.py --export-csv 导出的"已处理"CSV 直接画图，
不依赖 scipy/curve_fit，不重新拟合——单纯把已经算好的实测曲线、正弦拟合曲线、
容限带按原来的样式重新画一遍，用来复现同一张裁切后的对比图。

CSV 列（sine_fit_settling.py --export-csv 生成）：
    time_ms          画图用的时间轴（ms，已经是裁切/相对时间处理过的）
    measured_mV       实测差分电压
    sine_fit_mV       稳态正弦拟合曲线在该时刻的值
    tol_lower_mV/tol_upper_mV   ±tolerance 容限带上下界
    fit_A_mV/fit_f_Hz  拟合出的幅度/频率（每行重复，用于图例文字）
    fit_plot_start_ms  正弦拟合线/容限带从哪个时间开始画（之前的时间只画实测曲线）

用法
----
    python plot_from_processed_csv.py 14_hp200Hz_differential_cropped_processed.csv
"""

import argparse
import csv as csv_mod

import numpy as np


def load_processed_csv(path):
    with open(path, newline="") as f:
        rows = list(csv_mod.DictReader(f))
    if not rows:
        raise SystemExit(f"错误: {path} 里没有数据行。")
    t_ms = np.array([float(r["time_ms"]) for r in rows])
    measured = np.array([float(r["measured_mV"]) for r in rows])
    sine_fit = np.array([float(r["sine_fit_mV"]) for r in rows])
    tol_lo = np.array([float(r["tol_lower_mV"]) for r in rows])
    tol_hi = np.array([float(r["tol_upper_mV"]) for r in rows])
    A = float(rows[0]["fit_A_mV"])
    f = float(rows[0]["fit_f_Hz"])
    fit_plot_start_ms = float(rows[0]["fit_plot_start_ms"])
    return t_ms, measured, sine_fit, tol_lo, tol_hi, A, f, fit_plot_start_ms


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", help="sine_fit_settling.py --export-csv 生成的已处理 CSV")
    p.add_argument("--out", default=None, help="输出 PNG 路径，默认 <csv 同名前缀>.png")
    args = p.parse_args()

    t_ms, measured, sine_fit, tol_lo, tol_hi, A, f, fit_plot_start_ms = load_processed_csv(args.csv)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(t_ms, measured, color="#15761a", linewidth=0.8, label="Measured differential")

    fit_mask = t_ms >= fit_plot_start_ms
    ax.plot(t_ms[fit_mask], sine_fit[fit_mask], color="#c62828", linewidth=1.2, linestyle="--",
            label=f"Sine fit: A={A:.0f}, f={f:.1f} Hz")
    ax.fill_between(t_ms[fit_mask], tol_lo[fit_mask], tol_hi[fit_mask], color="#c62828", alpha=0.12)

    ax.set_xlim(t_ms[0], t_ms[-1])
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("Voltage (mV)")
    ax.set_title("Differential waveform vs sine fit")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()

    out_path = args.out or (args.csv.rsplit(".", 1)[0] + ".png")
    fig.savefig(out_path, dpi=150)
    print(f"已保存: {out_path}")


if __name__ == "__main__":
    main()
