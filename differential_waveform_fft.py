#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在 differential_waveform.py 原有处理流程之后，额外生成最终差分信号的 FFT 图。

原脚本的参数可以原样使用，例如：

    python differential_waveform_fft.py 14.wav --fs 500000 --baseline 0.004 --no-highpass

限制 FFT 显示频率范围（不影响 FFT 计算）：

    python differential_waveform_fft.py 14.wav --fs 500000 --baseline 0.004 \
        --no-highpass --fft-max-frequency 5000

输出：

    differential_waveform.py 原有的 CSV、总览图和局部放大图；
    *_differential_fft.png：最终差分波形的单边幅度频谱。

FFT 处理说明：

    1. 自动读取原脚本刚导出的 differential（或 differential_centered）列；
    2. FFT 前减去均值，去掉直流分量；
    3. 使用 Hann 窗降低非整周期截断造成的频谱泄漏；
    4. 按 Hann 窗的 coherent gain 修正，输出单边峰值幅度谱。
"""

import argparse
import csv
import io
import os
import re
import sys

import numpy as np

import differential_waveform


class _Tee(io.TextIOBase):
    """把原脚本输出照常显示，同时保存一份用于取得它导出的 CSV 路径。"""

    def __init__(self, stream):
        self.stream = stream
        self.buffer = io.StringIO()

    def write(self, text):
        self.stream.write(text)
        self.buffer.write(text)
        return len(text)

    def flush(self):
        self.stream.flush()

    def isatty(self):
        return self.stream.isatty()

    def getvalue(self):
        return self.buffer.getvalue()


def _split_fft_args(argv):
    """只取出本文件新增的参数，其余参数全部交给原脚本解析。"""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--fft-max-frequency",
        type=float,
        default=None,
        help="FFT 图横轴上限 Hz；默认显示到奈奎斯特频率",
    )
    return parser.parse_known_args(argv)


def _run_original(original_argv):
    """运行原脚本并返回它本次导出的差分 CSV 路径。"""
    saved_argv = sys.argv
    saved_stdout = sys.stdout
    tee = _Tee(saved_stdout)
    try:
        sys.argv = [saved_argv[0], *original_argv]
        sys.stdout = tee
        differential_waveform.main()
    finally:
        sys.argv = saved_argv
        sys.stdout = saved_stdout

    matches = re.findall(r"^已导出 CSV:\s*(.+?)\s*$", tee.getvalue(), flags=re.MULTILINE)
    if not matches:
        raise RuntimeError("未能从 differential_waveform.py 的输出中取得差分 CSV 路径。")
    return matches[-1]


def _load_differential_csv(csv_path):
    with open(csv_path, newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if not reader.fieldnames:
            raise ValueError(f"{csv_path} 没有 CSV 表头。")

        if "differential_centered" in reader.fieldnames:
            column = "differential_centered"
        elif "differential" in reader.fieldnames:
            column = "differential"
        else:
            raise ValueError(
                f"{csv_path} 中没有 differential 或 differential_centered 列。"
            )

        time_s = []
        differential = []
        for row in reader:
            time_s.append(float(row["time_s"]))
            differential.append(float(row[column]))

    t = np.asarray(time_s, dtype=np.float64)
    x = np.asarray(differential, dtype=np.float64)
    if len(t) < 4:
        raise ValueError("差分数据少于 4 个采样点，无法生成有意义的 FFT。")
    if not np.all(np.isfinite(t)) or not np.all(np.isfinite(x)):
        raise ValueError("差分 CSV 包含 NaN 或无穷值，无法执行 FFT。")

    dt = np.diff(t)
    if np.any(dt <= 0):
        raise ValueError("time_s 必须严格递增。")
    median_dt = float(np.median(dt))
    if not np.allclose(dt, median_dt, rtol=1e-5, atol=max(1e-15, median_dt * 1e-8)):
        raise ValueError("time_s 不是等间隔采样，不能直接执行普通 FFT。")

    return t, x, column, 1.0 / median_dt


def _one_sided_amplitude_spectrum(x, fs_hz):
    """返回经 Hann 窗幅值修正后的单边峰值幅度谱。"""
    n = len(x)
    x_ac = x - np.mean(x)
    window = np.hanning(n)
    coherent_gain = float(np.mean(window))
    spectrum = np.fft.rfft(x_ac * window)
    amplitude = np.abs(spectrum) / (n * coherent_gain)

    # 单边谱需要把正频率能量乘 2；DC 与偶数点 FFT 的 Nyquist 点不能乘 2。
    if n % 2 == 0:
        amplitude[1:-1] *= 2.0
    else:
        amplitude[1:] *= 2.0

    frequencies = np.fft.rfftfreq(n, d=1.0 / fs_hz)
    return frequencies, amplitude


def _save_fft_plot(csv_path, t, x, column, fs_hz, fft_max_frequency):
    frequencies, amplitude = _one_sided_amplitude_spectrum(x, fs_hz)
    nyquist = fs_hz / 2.0

    if fft_max_frequency is None:
        x_max = nyquist
    else:
        if fft_max_frequency <= 0:
            raise ValueError("--fft-max-frequency 必须大于 0 Hz。")
        x_max = min(float(fft_max_frequency), nyquist)
        if fft_max_frequency > nyquist:
            print(
                f"警告: --fft-max-frequency={fft_max_frequency:g} Hz 超过奈奎斯特频率 "
                f"{nyquist:g} Hz，已裁剪到 {nyquist:g} Hz。"
            )

    visible = (frequencies > 0) & (frequencies <= x_max)
    if not np.any(visible):
        raise ValueError(
            f"FFT 显示范围 0～{x_max:g} Hz 内没有非直流频点；"
            f"当前频率分辨率为 {fs_hz / len(x):g} Hz。"
        )

    visible_indices = np.flatnonzero(visible)
    peak_index = visible_indices[np.argmax(amplitude[visible])]
    peak_frequency = float(frequencies[peak_index])
    peak_amplitude = float(amplitude[peak_index])
    frequency_resolution = fs_hz / len(x)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.plot(frequencies[visible], amplitude[visible], color="#7b1fa2", linewidth=0.9)
    ax.plot(peak_frequency, peak_amplitude, "o", color="#d32f2f", markersize=5)
    ax.annotate(
        f"Peak: {peak_frequency:,.3f} Hz\nAmplitude: {peak_amplitude:.6g}",
        xy=(peak_frequency, peak_amplitude),
        xytext=(18, -48),
        textcoords="offset points",
        fontsize=9,
        color="#b71c1c",
        bbox=dict(facecolor="white", edgecolor="#d32f2f", alpha=0.85),
        arrowprops=dict(arrowstyle="->", color="#d32f2f"),
    )
    ax.set_xlim(0, x_max)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Peak amplitude (signal unit)")
    ax.set_title(
        "FFT of Differential Waveform\n"
        f"{column}, Hann window, N={len(x)}, fs={fs_hz:g} Sa/s, "
        f"resolution={frequency_resolution:g} Hz"
    )
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    stem = os.path.splitext(csv_path)[0]
    if stem.endswith("_differential"):
        stem = stem[: -len("_differential")]
    fft_path = stem + "_differential_fft.png"
    fig.savefig(fft_path, dpi=150)
    plt.close(fig)

    print(f"FFT 使用列: {column}（FFT 前已减均值并加 Hann 窗）")
    print(f"FFT 采样点数: {len(x)}, fs={fs_hz:g} Sa/s, 频率分辨率={frequency_resolution:g} Hz")
    print(f"FFT 显示范围内主峰: {peak_frequency:,.3f} Hz, 单边峰值幅度={peak_amplitude:.6g}")
    print(f"已保存差分 FFT 图: {fft_path}")
    return fft_path


def main():
    fft_args, original_argv = _split_fft_args(sys.argv[1:])
    if "-h" in original_argv or "--help" in original_argv:
        saved_argv = sys.argv
        try:
            sys.argv = [saved_argv[0], *original_argv]
            differential_waveform.parse_args()
        except SystemExit as exc:
            if exc.code == 0:
                print(
                    "\n本文件新增参数:\n"
                    "  --fft-max-frequency Hz  FFT 图横轴上限；默认显示到奈奎斯特频率"
                )
            raise
        finally:
            sys.argv = saved_argv

    csv_path = _run_original(original_argv)
    t, x, column, fs_hz = _load_differential_csv(csv_path)
    _save_fft_plot(csv_path, t, x, column, fs_hz, fft_args.fft_max_frequency)


if __name__ == "__main__":
    main()
