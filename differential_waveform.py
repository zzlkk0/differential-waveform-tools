#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
差分信号解算脚本 —— DPOS350P (FNIRSI 四合一平板示波器) 双通道 .wav 波形文件

背景说明
--------
示波器保存的 "*.wav" 并不是标准的 RIFF/PCM 音频 WAV（没有 "RIFF"/"WAVE" 头），
而是该机型自己的私有二进制转储格式，大致结构是：

    [0 .. ~56KB)   缩略图 + 头部/元数据块（含少量可解析的 32bit 大端整数字段，
                    其中一个字段的值和 CH1 数据起始偏移几乎精确吻合，
                    但没有找到官方文档，语义未知的字段不做强解读）
    [CH1 起始, CH1 结束)   CH1 原始采样，uint16，小端
    [~510 字节间隔]         可能是逐通道的测量值/统计块
    [CH2 起始, CH2 结束)   CH2 原始采样，uint16，小端（长度与 CH1 完全相同）
    [文件尾部 ~511 字节]    同上，未解析

以上结构是通过统计方式（在整份文件里找"数值平滑、方差有界"的连续段）反推出来的，
没有公开的官方格式文档，所以本脚本采用自动探测的方式定位两个通道的数据块，
而不是写死本文件里量出来的字节偏移 —— 这样即使你以后换一次采集（记录长度不同），
脚本大概率也能正常工作。如果探测失败，会打印警告，需要你手动调整。

关于刻度（volt/div、采样率）
----------------------------
两个通道的数据幅度跨度（max-min）在本文件里完全相等（都是 3839 个 ADC 码），
说明两个通道当时用的是相同的垂直档位（volts/div），只是垂直位置（偏移）不同，
偏移差正好是个几乎恒定的常数（约 7680 个码）。这个偏移是示波器为了把两条轨迹
在屏幕上分开显示而加的人为偏移，不是真实差分信号的一部分，所以脚本会分别使用
记录起始一段（默认前 4 ms）的均值平移整个 CH1/CH2，再做减法得到差分波形。

但因为格式里"多少个 ADC 码 = 1 格 = 多少伏"这个刻度字段，没能在没有官方文档的
情况下可靠解出来，所以下面 CONFIG 区的 VOLTS_PER_COUNT 缺省是 None
（=直接用原始 ADC 码作图，波形形状和相对幅度是对的，但纵轴不是"伏"）。
如果你知道采集时 CH1/CH2 的 volts/div 档位，把 VOLTS_PER_COUNT 填上就能得到
真正的伏特值；同理 SAMPLE_RATE_HZ 请填采集时的实际采样率（示波器屏幕上会显示，
或者由 time/div 档位推算），缺省先按 1 GSa/s（机器最大采样率）占位。

用法
----
    # 处理整段记录（原来的用法，不变）：
    python differential_waveform.py 5.wav

    # 一行命令：指定真实采样率、截取 15-20 秒、过 10Hz 一阶高通
    python differential_waveform.py 10.wav --fs 1000 --start 15 --end 20 --highpass 10

    --fs        采集时的真实采样率 (Sa/s)。这个私有格式里解不出来，必须自己填，
                不填就用下面 CONFIG 里的 SAMPLE_RATE_HZ 占位默认值。
    --start/--end   要截取的时间段（秒），相对整条记录的起点。不填就是全程。
    --baseline  用原始记录最前面多少秒的均值分别平移 CH1/CH2，默认 0.004 秒。
    --highpass  一阶高通滤波器的转折频率 (Hz)。命令行未指定时，交互运行会询问
                是否启用高通滤波；选择启用后再输入转折频率（高通角）。
    --no-highpass   明确关闭高通滤波并跳过交互询问，适合批处理。
    --order     滤波器阶数，默认 1（一阶，-6dB/oct），一般不用改。
"""

import argparse
import csv
import sys

import numpy as np

# ============================== CONFIG ===================================
# 命令行不传 --fs / --volts-per-count 时用下面这两个当默认值。
# 不知道就保持 None / 占位值，脚本会用"原始 ADC 码"画图（形状/相对幅度仍然正确）。
SAMPLE_RATE_HZ = 1e9          # 采集时的采样率（Sa/s）。不确定的话先按机器最大 1GSa/s 占位。
BASELINE_SECONDS = 0.004      # 用记录最前面这段时间的均值平移 CH1/CH2，默认 4 ms。
VOLTS_PER_COUNT = None        # 每个 ADC 码对应多少伏。None = 不做电压换算，只用原始码值。
CH1_NAME = "CH1 (V+)"
CH2_NAME = "CH2 (V-)"
# ===========================================================================


def find_smooth_runs(u16_array, diff_threshold=2000, min_run_len=500):
    """
    在 uint16 数组里找"相邻采样跳变很小"的连续区间 —— 真实模拟波形采样值
    逐点变化通常是平滑的，而头部/元数据字节被当成采样值解读时通常会有巨大跳变，
    可以用来把两者分开。返回按长度从大到小排序的 (start, end) 列表（end 不含）。
    """
    diff = np.abs(np.diff(u16_array.astype(np.int64)))
    smooth = diff < diff_threshold

    runs = []
    start = None
    for i, ok in enumerate(smooth):
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            runs.append((start, i + 1))  # +1 把两端点都包进采样区间
            start = None
    if start is not None:
        runs.append((start, len(smooth) + 1))

    runs = [r for r in runs if r[1] - r[0] >= min_run_len]
    runs.sort(key=lambda r: -(r[1] - r[0]))
    return runs


def split_merged_channel_run(u16_array, run, min_run_len=500, max_gap=2000,
                              center_frac=(0.35, 0.65)):
    """
    当 CH1/CH2 被误判成同一个平滑段时的补救：在该段内部重新定位两个通道
    数据块之间 ~510 字节的统计块间隔，以此为界把大段重新切成两段。

    为什么会需要它：find_smooth_runs 用一个固定跳变阈值（默认 2000 码）
    区分"真实模拟采样"和"两个通道数据块之间的间隔"。这在 AC 耦合时是可靠的，
    因为示波器为了把两条轨迹分开显示，会给 CH1/CH2 加一个几千码量级的人为
    垂直偏移，通道间隔处的跳变足够大，能稳定触发阈值。但在 DC 耦合、且两个
    通道使用相近的垂直 Offset（例如按 README 建议把两条轨迹都居中到同一档位）
    时，两个通道的真实电平本身就很接近，通道间隔处的跳变可能远小于 2000，
    会和真实信号一起被误判成同一个"平滑段"。

    做法：在该段内部对 find_smooth_runs 本身重新扫一遍递减的阈值，收集每个
    阈值下所有相邻子段之间的间隔。两个通道长度基本相等（都约等于整段的一半），
    所以真正的通道间隔必然落在整段中间一小块区域附近（默认 35%~65%）——
    只在这块"中央窗口"里找候选间隔，两端（比如某个通道内部一次真实信号的
    大幅跳变/尖峰）不算数，这样就不会被通道内部本身的瞬态误导。

    （早期版本没有限制搜索范围，直接找全段里跳变最大的一处；结果在某些
    DC 耦合数据里，通道内部一次真实的大信号跳变比通道间隔本身的跳变还大，
    被误当成了间隔，切出来的边界严重偏离真实通道边界。加上中央窗口限制后
    就不会再选中这类通道内部的瞬态。）

    候选间隔里优先选间隔最大的（切得最保守，最不容易把间隔里的数据算进
    CH1/CH2）。找到间隔后，直接把整段从间隔处切成两半（间隔前全部算 CH1，
    间隔后全部算 CH2），不要求间隔后半段本身还是一整个"平滑段"——因为半段
    内部完全可能还有真实信号自己的尖峰，只要间隔位置对了，把这些尖峰保留在
    对应通道里才是正确的。

    不依赖固定阈值，也不依赖任何硬编码的文件偏移。
    """
    rs, re = run
    seg = u16_array[rs:re]
    n = re - rs
    lo_bound, hi_bound = int(n * center_frac[0]), int(n * center_frac[1])

    candidates = []
    threshold = 2000.0
    while threshold >= 10.0:
        sub_runs = sorted(find_smooth_runs(seg, diff_threshold=threshold, min_run_len=min_run_len),
                           key=lambda r: r[0])
        for i in range(len(sub_runs) - 1):
            gap_start, gap_end = sub_runs[i][1], sub_runs[i + 1][0]
            gap_len = gap_end - gap_start
            gap_center = (gap_start + gap_end) / 2.0
            if 0 < gap_len <= max_gap and lo_bound <= gap_center <= hi_bound:
                r1, r2 = (rs, rs + gap_start), (rs + gap_end, re)
                if (r1[1] - r1[0]) >= min_run_len and (r2[1] - r2[0]) >= min_run_len:
                    candidates.append((gap_len, r1, r2))
        threshold *= 0.9

    if not candidates:
        # 最后兜底：中央窗口里找不到任何局部跳变异常（常见于两通道信号幅度/
        # 噪声水平本身就和通道间隔跳变差不多大的情况，例如信号幅度较小、
        # 量化台阶和间隔跳变同一量级，导致没有能可靠区分两者的候选缺口）。
        # 两个通道长度设计上相等，所以直接在合并段正中点切开，不再要求
        # 该处有跳变异常。这是最后手段，切分位置未必精确落在真实的
        # ~510 字节间隔上，请务必检查输出图形/CSV 两个通道是否正常。
        mid = n // 2
        r1, r2 = (rs, rs + mid), (rs + mid, re)
        if (r1[1] - r1[0]) >= min_run_len and (r2[1] - r2[0]) >= min_run_len:
            return r1, r2, (r1[1], r2[0])
        return None

    candidates.sort(key=lambda c: -c[0])
    gap_len, r1, r2 = candidates[0]
    gap = (r1[1], r2[0])
    return r1, r2, gap


def load_channels(path):
    data = open(path, "rb").read()
    print(f"文件大小: {len(data)} 字节")

    if data[:4] == b"RIFF":
        raise RuntimeError(
            "这个文件是标准 RIFF/WAV，不是示波器的私有格式，"
            "请直接用 scipy.io.wavfile 读取。"
        )

    n16 = len(data) // 2
    a = np.frombuffer(data[: n16 * 2], dtype="<u2")  # little-endian uint16

    runs = find_smooth_runs(a)
    if len(runs) < 2 and runs:
        # 常见于 DC 耦合数据：CH1/CH2 电平接近，通道间隔处的跳变没能触发固定阈值，
        # 两个通道被合并探测成了同一个平滑段，尝试用局部异常检测重新拆开。
        split = split_merged_channel_run(a, runs[0])
        if split is not None:
            r1, r2, gap = split
            print(
                f"警告: 自动探测只找到 1 个平滑数据段 {runs[0]}，"
                "怀疑是 DC 耦合下 CH1/CH2 电平接近导致通道间隔跳变过小、被合并。"
                f"已按段内局部异常位置重新拆分: CH1={r1}, 间隔{gap}({gap[1]-gap[0]} 点), CH2={r2}。"
                "请检查输出图形/CSV 两个通道是否正常，如不理想需要手动检查 find_smooth_runs 的阈值。"
            )
            runs = [r1, r2]

    if len(runs) < 2:
        raise RuntimeError(
            f"只探测到 {len(runs)} 个平滑数据段，需要至少 2 个（CH1/CH2）。"
            "文件格式可能和预期不一样，请检查 find_smooth_runs 的阈值。"
        )

    # 取最长的两段，按它们在文件中出现的先后顺序排（前面的当 CH1，后面的当 CH2）
    top2 = sorted(runs[:2], key=lambda r: r[0])
    (s1, e1), (s2, e2) = top2

    ch1_raw = a[s1:e1].astype(np.float64)
    ch2_raw = a[s2:e2].astype(np.float64)

    print(f"CH1 原始数据: 字节[{s1*2}:{e1*2}), {len(ch1_raw)} 个采样点, "
          f"范围 [{ch1_raw.min():.0f}, {ch1_raw.max():.0f}]")
    print(f"CH2 原始数据: 字节[{s2*2}:{e2*2}), {len(ch2_raw)} 个采样点, "
          f"范围 [{ch2_raw.min():.0f}, {ch2_raw.max():.0f}]")

    if len(ch1_raw) != len(ch2_raw):
        n = min(len(ch1_raw), len(ch2_raw))
        print(f"警告: 两通道长度不一致，截取到相同长度 {n} 个点")
        ch1_raw = ch1_raw[:n]
        ch2_raw = ch2_raw[:n]

    return ch1_raw, ch2_raw


def estimate_frequency(x, sample_rate_hz):
    """
    用 FFT 找主频，仅供参考。信号上如果叠加了 DAC 台阶噪声/毛刺，
    简单的过零点计数会被这些高频小毛刺干扰而报出错误的高频率，
    所以改用频谱里能量最大的非直流分量来估计基频，更稳健。
    """
    x = np.asarray(x) - np.mean(x)
    if len(x) < 8:
        return None
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    spec[0] = 0
    peak_bin = np.argmax(spec)
    if peak_bin == 0:
        return None
    freqs = np.fft.rfftfreq(len(x), d=1.0 / sample_rate_hz)
    return freqs[peak_bin]


def highpass_filter(x, cutoff_hz, fs_hz, order=1):
    """
    数字巴特沃斯高通滤波器（因果、单次正向滤波，scipy.signal.lfilter），
    不用 filtfilt —— filtfilt 会把信号正反各滤一次，等效阶数翻倍、
    和"一阶"的名义不符，这里保持真正的一阶（-6dB/oct）响应。
    """
    from scipy.signal import butter, lfilter

    nyq = fs_hz / 2.0
    if cutoff_hz <= 0 or cutoff_hz >= nyq:
        raise ValueError(
            f"高通转折频率 {cutoff_hz}Hz 必须在 (0, {nyq}Hz) 之间"
            f"（fs={fs_hz}Hz 时的奈奎斯特频率是 {nyq}Hz）"
        )
    b, a = butter(order, cutoff_hz / nyq, btype="highpass")
    return lfilter(b, a, x)


def notch_filter(x, notch_hz, fs_hz, order=4, q=30.0):
    """
    数字陷波滤波器（因果、单次正向滤波，scipy.signal.lfilter），用来去掉差分
    信号里的工频干扰（默认 50Hz）。

    scipy.signal.iirnotch 设计出来的是二阶陷波，这里按 order 级联
    order/2 个独立的二阶陷波节（都在同一个频率），凑成名义上的 order 阶，
    和 highpass_filter 里"阶数就是级联的二阶节数 x 2"的做法保持一致；
    同样不用 filtfilt，避免等效阶数翻倍。

    q 是每一节的品质因数（notch_hz / -3dB 陷波带宽），q 越大陷波越窄，
    对陷波频率附近的其它信号影响越小，但要求 notch_hz 本身足够准（比如
    真实工频有漂移，q 太大反而可能陷不干净）。
    """
    from scipy.signal import iirnotch, lfilter

    nyq = fs_hz / 2.0
    if notch_hz <= 0 or notch_hz >= nyq:
        raise ValueError(
            f"陷波频率 {notch_hz}Hz 必须在 (0, {nyq}Hz) 之间"
            f"（fs={fs_hz}Hz 时的奈奎斯特频率是 {nyq}Hz）"
        )
    if order < 2 or order % 2 != 0:
        raise ValueError("陷波滤波器阶数必须是大于等于 2 的偶数（由若干个二阶陷波级联而成）")
    if q <= 0:
        raise ValueError("陷波品质因数 q 必须大于 0")

    b, a = iirnotch(notch_hz, q, fs=fs_hz)
    y = x
    for _ in range(order // 2):
        y = lfilter(b, a, y)
    return y


def choose_highpass_cutoff(args, fs_hz):
    """解析命令行选项；必要时交互询问是否滤波以及高通转折频率。"""
    if args.highpass is not None:
        return args.highpass
    if args.no_highpass:
        return None

    # 重定向、管道和定时任务中不弹出问题，保持原有“默认不滤波”的行为。
    if not sys.stdin.isatty():
        return None

    while True:
        try:
            answer = input("是否启用高通滤波？[y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n未启用高通滤波。")
            return None

        if answer in ("", "n", "no", "否", "0"):
            return None
        if answer in ("y", "yes", "是", "1"):
            break
        print("请输入 y/是 来启用，或 n/否 来关闭。")

    nyq = fs_hz / 2.0
    while True:
        try:
            text = input(f"请输入高通转折频率（高通角），单位 Hz，范围 0～{nyq:g}: ").strip()
            cutoff_hz = float(text)
        except ValueError:
            print("请输入有效的数字。")
            continue
        except (EOFError, KeyboardInterrupt):
            print("\n已取消高通滤波。")
            return None

        if 0 < cutoff_hz < nyq:
            return cutoff_hz
        print(f"高通转折频率必须大于 0 且小于奈奎斯特频率 {nyq:g} Hz。")


def parse_args():
    p = argparse.ArgumentParser(
        description="解析示波器差分双通道 .wav，可选截取时间段 + 高通滤波，一行命令生成 CSV/图。"
    )
    p.add_argument("wav", nargs="?", default="5.wav", help="示波器 .wav 文件路径")
    p.add_argument("--fs", type=float, default=SAMPLE_RATE_HZ,
                    help=f"采样率 Sa/s（该私有格式解不出来，需自己填；默认占位值 {SAMPLE_RATE_HZ:g}）")
    p.add_argument("--start", type=float, default=None, help="截取起始时间，秒（默认整条记录开头）")
    p.add_argument("--end", type=float, default=None, help="截取结束时间，秒（默认整条记录结尾）")
    p.add_argument(
        "--baseline", "--baseline-seconds", dest="baseline_seconds", type=float,
        default=BASELINE_SECONDS,
        help=f"用原始记录最前面多少秒的均值分别平移 CH1/CH2（默认 {BASELINE_SECONDS:g} 秒）"
    )
    p.add_argument(
        "--diff-center-start", type=float, default=None,
        help="用于估计差分正弦中心的稳态区间起点（秒，需与 --diff-center-end 同时使用）"
    )
    p.add_argument(
        "--diff-center-end", type=float, default=None,
        help="用于估计差分正弦中心的稳态区间终点（秒，需与 --diff-center-start 同时使用）"
    )
    highpass_group = p.add_mutually_exclusive_group()
    highpass_group.add_argument(
        "--highpass", type=float, default=None,
        help="启用高通滤波并指定转折频率 Hz；不指定时交互询问"
    )
    highpass_group.add_argument(
        "--no-highpass", action="store_true",
        help="关闭高通滤波并跳过交互询问"
    )
    p.add_argument("--order", type=int, default=1, help="高通滤波器阶数（默认 1 = 一阶）")
    p.add_argument(
        "--notch", type=float, default=None, nargs="?", const=50.0,
        help="启用陷波滤波，去掉差分信号里的工频干扰；单独写 --notch 默认 50Hz，"
             "也可以写 --notch 60 指定频率"
    )
    p.add_argument("--notch-order", type=int, default=4,
                    help="陷波滤波器阶数，必须是大于等于2的偶数（默认 4，由 2 个二阶陷波级联而成）")
    p.add_argument("--notch-q", type=float, default=30.0,
                    help="陷波品质因数，越大陷波越窄（默认 30）")
    p.add_argument("--volts-per-count", type=float, default=VOLTS_PER_COUNT,
                    help="每个 ADC 码对应多少伏，不填用原始码值")
    return p.parse_args()


def main():
    args = parse_args()
    path = args.wav
    fs = args.fs
    if fs <= 0:
        raise SystemExit("错误: 采样率 --fs 必须大于 0。")
    if args.baseline_seconds <= 0:
        raise SystemExit("错误: 起始基准时长 --baseline 必须大于 0 秒。")
    if (args.diff_center_start is None) != (args.diff_center_end is None):
        raise SystemExit("错误: --diff-center-start 和 --diff-center-end 必须同时使用。")
    if args.diff_center_start is not None and args.diff_center_start >= args.diff_center_end:
        raise SystemExit("错误: 差分居中区间的起点必须小于终点。")
    if args.order < 1:
        raise SystemExit("错误: 滤波器阶数 --order 必须是大于等于 1 的整数。")
    if args.notch is not None:
        if args.notch <= 0 or args.notch >= fs / 2:
            raise SystemExit(
                f"错误: 陷波频率 --notch {args.notch:g}Hz 必须在 (0, {fs/2:g}Hz) 之间"
                f"（fs={fs:g}Hz 时的奈奎斯特频率是 {fs/2:g}Hz）。"
            )
        if args.notch_order < 2 or args.notch_order % 2 != 0:
            raise SystemExit("错误: 陷波滤波器阶数 --notch-order 必须是大于等于 2 的偶数。")
        if args.notch_q <= 0:
            raise SystemExit("错误: 陷波品质因数 --notch-q 必须大于 0。")
    highpass_hz = choose_highpass_cutoff(args, fs)

    ch1_raw, ch2_raw = load_channels(path)
    n_total = len(ch1_raw)
    duration = n_total / fs
    print(f"\n采样率 fs={fs:g} Sa/s -> 整条记录时长 {duration*1000:.3f} ms ({duration:.6f} s)")

    # ---- 先用整条记录起始窗口的均值，分别平移 CH1/CH2 的全部样本 ----
    baseline_n = max(1, int(round(args.baseline_seconds * fs)))
    if baseline_n > n_total:
        print(
            f"警告: 基准时长 {args.baseline_seconds:g} s 超过整条记录 {duration:g} s，"
            "已使用整条记录求均值"
        )
        baseline_n = n_total
    baseline_actual_s = baseline_n / fs
    ch1_baseline = ch1_raw[:baseline_n].mean()
    ch2_baseline = ch2_raw[:baseline_n].mean()
    ch1_shifted = ch1_raw - ch1_baseline
    ch2_shifted = ch2_raw - ch2_baseline
    print(
        f"起始基准: 前 {baseline_actual_s:g} s（{baseline_n} 点）；"
        f"CH1 均值={ch1_baseline:.3f}, CH2 均值={ch2_baseline:.3f}，已分别整体平移到 0"
    )

    # ---- 平移后再按时间段截取 ----
    start_s = 0.0 if args.start is None else args.start
    end_s = duration if args.end is None else args.end
    if start_s < 0 or end_s > duration or start_s >= end_s:
        print(f"警告: 请求的区间 [{start_s}, {end_s}] s 超出记录范围 [0, {duration:.6f}] s，已自动裁剪")
    start_s = max(0.0, min(start_s, duration))
    end_s = max(0.0, min(end_s, duration))
    i0 = int(round(start_s * fs))
    i1 = int(round(end_s * fs))
    i0 = max(0, min(i0, n_total))
    i1 = max(0, min(i1, n_total))
    if i1 - i0 < 2:
        raise SystemExit(
            f"错误: 请求的区间 [{start_s:.6f}, {end_s:.6f}] s 在 fs={fs:g} Sa/s 下和整条记录"
            f" [0, {duration:.6f}] s 几乎没有交集，只剩 {max(0, i1-i0)} 个采样点，无法继续。"
            f" 请检查 --fs / --start / --end 是否正确（比如是不是把 s 和 ms 搞混了）。"
        )
    if args.start is not None or args.end is not None:
        print(f"截取区间: [{start_s:.6f}, {end_s:.6f}] s -> 采样点 [{i0}:{i1}) 共 {i1-i0} 点")

    ch1_ac = ch1_shifted[i0:i1]
    ch2_ac = ch2_shifted[i0:i1]
    n = len(ch1_ac)
    t = (np.arange(n) + i0) / fs

    if args.volts_per_count is not None:
        ch1_v = ch1_ac * args.volts_per_count
        ch2_v = ch2_ac * args.volts_per_count
        unit = "V"
        unit_plot = "V"
    else:
        ch1_v = ch1_ac
        ch2_v = ch2_ac
        unit = "ADC counts (未校准)"
        unit_plot = "ADC counts, uncalibrated"

    # ---- 先计算差分，再只对差分信号做高通滤波；CH1/CH2 保持未滤波 ----
    diff = ch1_v - ch2_v  # 差分信号 = V+ - V-

    tag = ""
    if highpass_hz is not None:
        diff = highpass_filter(diff, highpass_hz, fs, args.order)
        print(f"已对差分信号应用 {args.order} 阶高通滤波器, 转折频率 {highpass_hz:g} Hz")
        tag = f"_hp{highpass_hz:g}Hz"

    # ---- 可选：陷波滤波，去掉差分信号里的工频干扰（默认 50Hz）；同样只作用于
    #      差分结果，CH1/CH2 保持不变。在高通之后做，避免高通滤波器边沿转折
    #      频率附近的相位/幅度响应影响陷波深度。----
    if args.notch is not None:
        diff = notch_filter(diff, args.notch, fs, args.notch_order, args.notch_q)
        print(f"已对差分信号应用 {args.notch_order} 阶陷波滤波器, 陷波频率 {args.notch:g} Hz, Q={args.notch_q:g}")
        tag += f"_notch{args.notch:g}Hz"

    # 可选：用稳态区间的 1%/99% 分位中点，将差分正弦中心平移到 0。
    # 保留未居中的差分用于 CSV 对照，图中显示居中后的差分。
    diff_uncentered = None
    diff_center = None
    if args.diff_center_start is not None:
        center_i0 = int(round(args.diff_center_start * fs)) - i0
        center_i1 = int(round(args.diff_center_end * fs)) - i0
        if center_i0 < 0 or center_i1 > n or center_i1 - center_i0 < 2:
            raise SystemExit(
                "错误: 差分居中区间必须完整包含在 --start/--end 的输出区间内，且至少包含 2 个采样点。"
            )
        center_segment = diff[center_i0:center_i1]
        center_low = np.percentile(center_segment, 1.0)
        center_high = np.percentile(center_segment, 99.0)
        diff_center = (center_low + center_high) / 2.0
        diff_uncentered = diff.copy()
        diff = diff - diff_center
        tag += "_centered"
        print(
            f"差分稳态居中: 区间 [{args.diff_center_start:g}, {args.diff_center_end:g}] s, "
            f"P1={center_low:.3f}, P99={center_high:.3f}, 中心={diff_center:.3f} {unit}"
        )

    freq1 = estimate_frequency(ch1_v, fs)
    freq_diff = estimate_frequency(diff, fs)
    print(f"\n单位: {unit}")
    print(f"CH1  Vpp = {ch1_v.max()-ch1_v.min():.3f} {unit}")
    print(f"CH2  Vpp = {ch2_v.max()-ch2_v.min():.3f} {unit}")
    print(f"差分 Vpp = {diff.max()-diff.min():.3f} {unit}")
    if freq1:
        print(f"CH1 估计频率  ~ {freq1:,.3f} Hz (按 fs={fs:g} 计算)")
    if freq_diff:
        print(f"差分估计频率  ~ {freq_diff:,.3f} Hz")

    # ---- 输出文件名：带上截取区间/滤波信息，避免覆盖掉全程未滤波的结果 ----
    stem = path.rsplit(".", 1)[0]
    if args.start is not None or args.end is not None:
        stem += f"_{start_s:g}-{end_s:g}s"
    stem += tag

    # 导出 CSV
    csv_path = stem + "_differential.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        if diff_uncentered is None:
            w.writerow(["time_s", "ch1", "ch2", "differential"])
            for i in range(n):
                w.writerow([t[i], ch1_v[i], ch2_v[i], diff[i]])
        else:
            w.writerow(["time_s", "ch1", "ch2", "differential_uncentered", "differential_centered"])
            for i in range(n):
                w.writerow([t[i], ch1_v[i], ch2_v[i], diff_uncentered[i], diff[i]])
    print(f"\n已导出 CSV: {csv_path}")

    # 画图
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        # x轴单位按这段时长自适应挑（s / ms / us），避免采样率一低，微秒刻度就变成一长串大数字
        span_s = t[-1] - t[0] if n > 1 else 1.0 / fs
        if span_s >= 1:
            xscale, xunit = 1.0, "s"
        elif span_s >= 1e-3:
            xscale, xunit = 1e3, "ms"
        else:
            xscale, xunit = 1e6, "us"
        t_plot = t * xscale

        fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
        axes[0].plot(t_plot, ch1_v, color="#e07b39", linewidth=0.8)
        axes[0].set_ylabel(f"{CH1_NAME}\n({unit_plot})")
        title = "Oscilloscope Channels & Differential Waveform"
        if highpass_hz is not None:
            title += f"  (differential: order-{args.order} HPF @ {highpass_hz:g} Hz)"
        if args.notch is not None:
            title += f"  (order-{args.notch_order} notch @ {args.notch:g} Hz, Q={args.notch_q:g})"
        if diff_center is not None:
            title += "  (differential centered by steady-state P1/P99)"
        axes[0].set_title(title)

        axes[1].plot(t_plot, ch2_v, color="#3b82c4", linewidth=0.8)
        axes[1].set_ylabel(f"{CH2_NAME}\n({unit_plot})")

        axes[2].plot(t_plot, diff, color="#2e7d32", linewidth=0.8)
        diff_label = "CH1 - CH2 (centered)" if diff_center is not None else "CH1 - CH2"
        axes[2].set_ylabel(f"{diff_label}\n({unit_plot})")
        axes[2].set_xlabel(f"Time ({xunit})")

        for ax in axes:
            ax.grid(True, alpha=0.3)

        fig.tight_layout()
        png_path = stem + "_differential.png"
        fig.savefig(png_path, dpi=150)
        print(f"已保存总览图: {png_path}")

        # 局部放大图：整条记录点数很多，全局图里单个周期会挤在一起看不清，
        # 额外存一张只画开头几个周期的放大图，方便确认差分极性/波形细节。
        zoom_n = min(n, 600)
        fig2, ax2 = plt.subplots(figsize=(11, 4))
        idx = np.arange(zoom_n)
        ax2.plot(idx, ch1_v[:zoom_n], label=CH1_NAME, color="#e07b39", linewidth=1)
        ax2.plot(idx, ch2_v[:zoom_n], label=CH2_NAME, color="#3b82c4", linewidth=1)
        zoom_diff_label = "CH1 - CH2 (centered)" if diff_center is not None else "CH1 - CH2 (differential)"
        ax2.plot(idx, diff[:zoom_n], label=zoom_diff_label, color="#2e7d32", linewidth=1.2)
        ax2.set_xlabel("Sample index")
        ax2.set_ylabel(f"{unit_plot}")
        ax2.set_title("Zoomed-in view (first samples) — check differential polarity/shape")
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        fig2.tight_layout()
        zoom_path = stem + "_differential_zoom.png"
        fig2.savefig(zoom_path, dpi=150)
        print(f"已保存局部放大图: {zoom_path}")
    except ImportError:
        print("未安装 matplotlib，跳过画图（pip install matplotlib 后重跑即可出图）。")


if __name__ == "__main__":
    main()
