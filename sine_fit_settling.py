#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用差分波形 CSV（differential_waveform.py 的输出）中"靠后、已经稳定"的若干个周期
拟合出一个标准正弦波，再把这个理想稳态正弦波往前延伸，和实际波形叠加对比，
用来估计起振/建立时间（settling time）。

用法
----
    python sine_fit_settling.py 12_differential.csv --view-start 0.017 --view-end 0.023497

    --view-start/--view-end   分析用的时间窗口（秒），默认整份 CSV；决定自动找
                                拟合周期、起振/建立时间判定的取值范围。
    --fit-cycles              自动模式下，用窗口末尾第几个完整周期开始拟合，
                                默认最后 3 个周期（--fit-window-start/-end 给了之
                                后这个参数被忽略）。
    --fit-window-start/--fit-window-end
                                直接指定用来做 curve_fit 的波形区间（绝对时间，
                                秒），跳过"自动找窗口末尾周期"这一步。
    --tolerance                建立时间判据：每周期半幅度和稳态半幅度的相对误差
                                容限，默认 0.05（±5%）。
    --column                   CSV 里要用哪一列做差分信号，默认自动选择
                                differential_centered（如果存在）否则 differential。
    --plot-xlim-start/--plot-xlim-end
                                画图显示范围（秒），默认等于 --view-start/-end；
                                可以比分析窗口更窄，纯裁切显示，不影响拟合结果。
    --x-relative               横轴改成相对 --plot-xlim-start 的时间（ms，从 0
                                开始），默认用绝对时间。
    --fit-plot-start           正弦拟合线/容限带只从这个时刻（绝对时间，秒）开
                                始画，默认等于 --view-start。
    --fit-shift                把正弦拟合线/容限带在时间轴上前移这么多秒（正值
                                = 前移/更早出现），只平移画图，不改变 A/f/phi/C。
    --vline                    在图上画一条竖直参考线（绝对时间，秒），可重复
                                传多次；传 2 条或以上会在相邻两条之间标出间隔。
    --figsize                  图尺寸，英寸，格式 宽,高，默认 12,5。
    --font-scale               标题/坐标轴/刻度/图例/标注文字整体放大倍数，默认 1.0。
    --out-suffix                输出文件名后缀（不含 .png），默认 _sine_fit。
    --export-csv               把图上显示范围内的数据（实测值 + 正弦拟合值 +
                                容限带上下界）导出成 CSV，配合
                                plot_from_processed_csv.py 可以不重新拟合就画出
                                同一张图。

输出
----
    <csv 同名前缀><out-suffix>.png   实测波形 + 延伸后的理想正弦波 + 容限带
                                        （+ 竖直参考线/间隔标注，如果给了 --vline）
    终端打印：拟合频率/幅度/相位、起振时刻、建立时间
    （--export-csv 给了的话）额外输出处理后的 CSV，配合 plot_from_processed_csv.py
    使用
"""

import argparse
import csv as csv_mod
import sys

import numpy as np


def load_csv(path, column=None):
    with open(path, newline="") as f:
        r = csv_mod.DictReader(f)
        rows = list(r)
    t = np.array([float(row["time_s"]) for row in rows])
    if column is None:
        fieldnames = rows[0].keys()
        column = "differential_centered" if "differential_centered" in fieldnames else "differential"
    d = np.array([float(row[column]) for row in rows])
    return t, d, column


def median_filter3(x):
    """长度 3 的中值滤波，去掉孤立的单点掉数尖峰（该私有格式偶尔出现的毛刺），
    不用 scipy 是为了减少依赖；边界样本原样保留。"""
    y = x.copy()
    y[1:-1] = np.median(np.stack([x[:-2], x[1:-1], x[2:]]), axis=0)
    return y


def sine_model(t, A, f, phi, C):
    return A * np.sin(2 * np.pi * f * t + phi) + C


def find_up_crossings(t, d, center):
    """在 d-center 的正向过零点做线性插值，返回过零时刻数组。"""
    s = d - center
    idx = np.where((s[:-1] < 0) & (s[1:] >= 0))[0]
    out = []
    for i in idx:
        t0, t1 = t[i], t[i + 1]
        s0, s1 = s[i], s[i + 1]
        out.append(t0 + (0 - s0) * (t1 - t0) / (s1 - s0))
    return np.array(out)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", help="differential_waveform.py 生成的 *_differential.csv")
    p.add_argument("--view-start", type=float, default=None, help="分析/画图窗口起点，秒")
    p.add_argument("--view-end", type=float, default=None, help="分析/画图窗口终点，秒")
    p.add_argument("--fit-cycles", type=int, default=3, help="用窗口末尾最后几个完整周期做拟合，默认 3")
    p.add_argument("--tolerance", type=float, default=0.05, help="建立时间判据的相对幅度容限，默认 0.05")
    p.add_argument("--column", default=None, help="CSV 中用作差分信号的列名，默认自动选择")
    p.add_argument("--no-medfilt", action="store_true", help="不做单点毛刺中值滤波")
    p.add_argument("--plot-xlim-start", type=float, default=None,
                    help="画图显示范围的起点（秒），默认等于 --view-start；不影响拟合/分析窗口")
    p.add_argument("--plot-xlim-end", type=float, default=None,
                    help="画图显示范围的终点（秒），默认等于 --view-end；不影响拟合/分析窗口")
    p.add_argument("--x-relative", action="store_true",
                    help="横轴改成相对 --plot-xlim-start 的时间（ms，从 0 开始），默认用绝对时间")
    p.add_argument("--fit-plot-start", type=float, default=None,
                    help="正弦拟合线/容限带只从这个时刻（秒）开始画，默认等于 --view-start；不影响拟合本身")
    p.add_argument("--fit-shift", type=float, default=0.0,
                    help="把正弦拟合线/容限带在时间轴上前移这么多秒（正值=前移/更早出现），"
                         "只是画图上整体平移曲线，不改变 A/f/phi/C 本身")
    p.add_argument("--out-suffix", default="_sine_fit",
                    help="输出文件名后缀（不含 .png），默认 _sine_fit")
    p.add_argument("--export-csv", default=None,
                    help="把图上显示范围内的数据（实测值 + 正弦拟合值 + 容限带上下界）导出成 CSV，"
                         "配合 plot_from_processed_csv.py 可以不重新拟合就画出同一张图")
    p.add_argument("--vline", type=float, action="append", default=None,
                    help="在图上画一条竖直参考线，时刻用绝对时间（秒），可以重复传多次；"
                         "传 2 条或以上时会在相邻两条之间标出时间间隔")
    p.add_argument("--figsize", default="12,5",
                    help="图尺寸，英寸，格式 宽,高，默认 12,5；4:3 可以传 12,9")
    p.add_argument("--font-scale", type=float, default=1.0,
                    help="标题/坐标轴/刻度/图例/标注文字整体放大倍数，默认 1.0")
    p.add_argument("--fit-window-start", type=float, default=None,
                    help="直接指定用来做 curve_fit 的波形区间起点（绝对时间，秒）；"
                         "给了这个就不再自动找窗口末尾的周期，--fit-cycles 也会被忽略")
    p.add_argument("--fit-window-end", type=float, default=None,
                    help="直接指定用来做 curve_fit 的波形区间终点（绝对时间，秒），要和 --fit-window-start 一起给")
    args = p.parse_args()

    t, d, column = load_csv(args.csv, args.column)
    print(f"读取 {args.csv} 的列: {column}，共 {len(t)} 点，时间范围 [{t[0]*1000:.4f}, {t[-1]*1000:.4f}] ms")

    d_f = d if args.no_medfilt else median_filter3(d)

    view_start = t[0] if args.view_start is None else args.view_start
    view_end = t[-1] if args.view_end is None else args.view_end
    vmask = (t >= view_start) & (t <= view_end)
    if vmask.sum() < 10:
        raise SystemExit("错误: 窗口内点数太少，请检查 --view-start/--view-end。")
    tv, dv = t[vmask], d_f[vmask]

    if args.fit_window_start is not None and args.fit_window_end is not None:
        # ---- 直接使用指定的区间做拟合，不自动找窗口末尾的周期 ----
        fit_t0, fit_t1 = args.fit_window_start, args.fit_window_end
        fmask = (tv >= fit_t0) & (tv <= fit_t1)
        ft, fd = tv[fmask], dv[fmask]
        if len(ft) < 10:
            raise SystemExit(
                f"错误: --fit-window-start/--fit-window-end 指定的区间 [{fit_t0*1000:.4f}, "
                f"{fit_t1*1000:.4f}] ms 内点数太少（{len(ft)} 个），检查是不是超出了 --view-start/--view-end。"
            )
        print(f"\n用于拟合的指定区间: [{fit_t0*1000:.4f}, {fit_t1*1000:.4f}] ms, {len(ft)} 点")
    else:
        # ---- 第一步：粗略估计窗口末尾的周期，找末尾若干个完整周期作为拟合区间 ----
        rough_center = np.median(dv[-max(50, len(dv) // 4):])
        tail_cross = find_up_crossings(tv, dv, rough_center)
        if len(tail_cross) < args.fit_cycles + 1:
            raise SystemExit(
                f"错误: 窗口末尾只找到 {len(tail_cross)} 个过零点，不够拟合 {args.fit_cycles} 个完整周期。"
            )
        fit_t0 = tail_cross[-(args.fit_cycles + 1)]
        fit_t1 = tail_cross[-1]
        fmask = (tv >= fit_t0) & (tv <= fit_t1)
        ft, fd = tv[fmask], dv[fmask]
        print(f"\n用于拟合的最后 {args.fit_cycles} 个周期: [{fit_t0*1000:.4f}, {fit_t1*1000:.4f}] ms, {len(ft)} 点")

    # ---- 第二步：非线性最小二乘拟合标准正弦 A*sin(2*pi*f*t+phi)+C ----
    from scipy.optimize import curve_fit

    fit_crossings = find_up_crossings(ft, fd, np.median(fd))
    if len(fit_crossings) >= 2:
        period0 = (fit_crossings[-1] - fit_crossings[0]) / (len(fit_crossings) - 1)
    else:
        period0 = (fit_t1 - fit_t0) / args.fit_cycles
    f0 = 1.0 / period0
    A0 = (fd.max() - fd.min()) / 2
    C0 = fd.mean()
    popt, pcov = curve_fit(sine_model, ft, fd, p0=[A0, f0, 0.0, C0], maxfev=20000)
    A, f, phi, C = popt
    perr = np.sqrt(np.diag(pcov))
    resid = fd - sine_model(ft, *popt)
    print(
        f"拟合结果: A={A:.3f}±{perr[0]:.3f}, f={f:.4f}±{perr[1]:.4f} Hz, "
        f"phi={phi:.4f} rad, C={C:.3f}\n"
        f"拟合区间残差: std={resid.std():.3f}, 最大绝对值={np.abs(resid).max():.3f} "
        f"(相对幅度 {np.abs(resid).max()/abs(A)*100:.1f}%)"
    )

    # ---- 起振时刻: 用整条记录里公认安静的一段估计基线噪声水平（不能用 tv 窗口
    #      本身，因为 --view-start 常常就已经晚于起振点，窗口内的"基线"段
    #      可能已经混进了起振瞬态，会把噪声水平算得偏大导致起振点测不出来）----
    quiet_mask = t < min(t[0] + 0.005, view_start)
    baseline_std = d_f[quiet_mask].std() if quiet_mask.sum() >= 10 else d_f[: len(d_f) // 20].std()
    dev = np.abs(dv - C)
    onset_candidates = np.where(dev > 5 * baseline_std)[0]
    onset_t = tv[onset_candidates[0]] if len(onset_candidates) else None
    if onset_t is not None:
        print(f"\n起振时刻（首次偏离基线 > 5倍基线噪声）: {onset_t*1000:.4f} ms")
    else:
        print("\n警告: 未能在窗口内找到明显的起振点，--view-start 可能已经晚于起振。")

    # ---- 建立时间: 逐周期计算实测半幅度 / 拟合稳态半幅度 A 的比值，
    #      找到"从此以后所有周期都落在 ±tolerance 容限带内"的最早周期 ----
    all_cross = find_up_crossings(tv, dv, C)
    target_A = abs(A)
    cycles = []
    for i in range(len(all_cross) - 1):
        c0, c1 = all_cross[i], all_cross[i + 1]
        seg = dv[(tv >= c0) & (tv < c1)]
        if len(seg) < 3:
            continue
        half_amp = (seg.max() - seg.min()) / 2
        cycles.append((c0, c1, half_amp, half_amp / target_A))

    settle_t = None
    for i, (c0, c1, ha, ratio) in enumerate(cycles):
        if all(abs(r - 1.0) <= args.tolerance for _, _, _, r in cycles[i:]):
            settle_t = c0
            break

    print(f"\n逐周期幅度 (目标稳态半幅度 |A|={target_A:.1f}):")
    for c0, c1, ha, ratio in cycles:
        flag = "  <- 建立时间" if settle_t is not None and abs(c0 - settle_t) < 1e-9 else ""
        print(f"  [{c0*1000:8.4f}, {c1*1000:8.4f}] ms  半幅度={ha:7.1f}  比例={ratio:5.3f}{flag}")

    if settle_t is not None:
        print(f"\n建立时间判据: 相对幅度容限 ±{args.tolerance*100:.0f}%")
        print(f"  进入并保持容限带的时刻: {settle_t*1000:.4f} ms")
        if onset_t is not None:
            print(f"  相对起振点 ({onset_t*1000:.4f} ms) 的建立时间: {(settle_t-onset_t)*1000:.4f} ms")
    else:
        print(f"\n警告: 在 ±{args.tolerance*100:.0f}% 容限下，窗口内没有一个周期能保持到结尾都合格，"
              "说明幅度起伏本身超过了这个容限（可能是真实信号噪声/谐波，不是单纯的建立过程）。")

    # ---- 画图 ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_w, fig_h = (float(v) for v in args.figsize.split(","))
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    # 画图显示范围（可以比分析窗口 view_start/view_end 更窄），不影响上面的拟合结果
    x0 = args.plot_xlim_start if args.plot_xlim_start is not None else view_start
    x1 = args.plot_xlim_end if args.plot_xlim_end is not None else view_end
    t_ms = (tv - x0) * 1000 if args.x_relative else tv * 1000

    ax.plot(t_ms, dv, color="#15761a", linewidth=0.8, label="Measured differential") #

    ideal = sine_model(tv + args.fit_shift, A, f, phi, C)
    fit_plot_start = args.fit_plot_start if args.fit_plot_start is not None else view_start
    fit_mask = tv >= fit_plot_start
    ax.plot(t_ms[fit_mask], ideal[fit_mask], color="#c62828", linewidth=1.2, linestyle="--",
            label=f"Sine fit: A={A:.0f}, f={f:.1f} Hz")#
    ax.fill_between(t_ms[fit_mask], (ideal - args.tolerance * abs(A))[fit_mask],
                     (ideal + args.tolerance * abs(A))[fit_mask],
                     color="#c62828", alpha=0.12) # , label=f"±{args.tolerance*100:.0f}% tolerance band"

    ax.set_xlim((0, (x1 - x0) * 1000) if args.x_relative else (x0 * 1000, x1 * 1000))

    if args.vline:
        vlines_abs = sorted(args.vline)
        vlines_x = [((v - x0) * 1000 if args.x_relative else v * 1000) for v in vlines_abs]
        for vx in vlines_x:
            ax.axvline(vx, color="#1565c0", linewidth=1.2, linestyle="--")
        ylim = ax.get_ylim()
        y_annot = ylim[1] - 0.08 * (ylim[1] - ylim[0])
        for i in range(len(vlines_x) - 1):
            xa, xb = vlines_x[i], vlines_x[i + 1]
            dt_ms = xb - xa
            ax.annotate("", xy=(xa, y_annot), xytext=(xb, y_annot),
                        arrowprops=dict(arrowstyle="<->", color="#1565c0"))
            ax.text((xa + xb) / 2, y_annot, f"{dt_ms:.4f} ms", color="#1565c0",
                    ha="center", va="bottom", fontsize=9 * args.font_scale,
                    bbox=dict(facecolor="white", edgecolor="none", alpha=0.75, pad=1))

    if args.export_csv:
        disp_mask = (tv >= x0) & (tv <= x1)
        tol_lo = ideal - args.tolerance * abs(A)
        tol_hi = ideal + args.tolerance * abs(A)
        with open(args.export_csv, "w", newline="") as csv_f:
            w = csv_mod.writer(csv_f)
            w.writerow(["time_ms", "measured_mV", "sine_fit_mV", "tol_lower_mV", "tol_upper_mV",
                        "fit_A_mV", "fit_f_Hz", "fit_plot_start_ms"])
            fit_plot_start_ms = (fit_plot_start - x0) * 1000 if args.x_relative else fit_plot_start * 1000
            for tm, m, s, lo, hi in zip(t_ms[disp_mask], dv[disp_mask], ideal[disp_mask],
                                         tol_lo[disp_mask], tol_hi[disp_mask]):
                w.writerow([f"{tm:.6f}", f"{m:.4f}", f"{s:.4f}", f"{lo:.4f}", f"{hi:.4f}",
                            f"{A:.4f}", f"{f:.4f}", f"{fit_plot_start_ms:.4f}"])
        print(f"已导出画图数据: {args.export_csv}")


    # ax.axvspan(fit_t0 * 1000, fit_t1 * 1000, color="#1565c0", alpha=0.08, label="Cycles used for fit")
    # if onset_t is not None:
    #     ax.axvline(onset_t * 1000, color="#f57c00", linewidth=1.2, linestyle=":", label=f"Onset {onset_t*1000:.3f} ms")
    # if settle_t is not None:
    #     ax.axvline(settle_t * 1000, color="#6a1b9a", linewidth=1.2, linestyle=":", label=f"Settled {settle_t*1000:.3f} ms")

    ax.set_xlabel("Time (ms)", fontsize=13 * args.font_scale)
    ax.set_ylabel("Voltage (mV)", fontsize=13 * args.font_scale)
    title = "Differential waveform vs sine fit"
    # if onset_t is not None and settle_t is not None:
    #     title += f"\nsettling time ≈ {(settle_t-onset_t)*1000:.3f} ms (±{args.tolerance*100:.0f}% band)"
    ax.set_title(title, fontsize=16 * args.font_scale)
    ax.grid(True, alpha=0.3)
    ax.tick_params(axis="both", labelsize=11 * args.font_scale)
    ax.legend(loc="upper right", fontsize=11 * args.font_scale)
    fig.tight_layout()

    stem = args.csv.rsplit(".", 1)[0]
    out_path = stem + args.out_suffix + ".png"
    fig.savefig(out_path, dpi=150)
    print(f"\n已保存拟合对比图: {out_path}")


if __name__ == "__main__":
    main()
