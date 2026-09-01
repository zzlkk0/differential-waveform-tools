差分波形处理脚本使用说明
========================

适用设备：FNIRSI DPOS350P
-------------------------

本项目用于处理 FNIRSI（菲尼瑞斯）DPOS350P 四合一多功能平板示波器导出的
双通道波形文件。根据设备配套说明书，DPOS350P 集以下功能于一体：

    双通道数字荧光示波器：最高 1 GSa/s 实时采样率，350 MHz 模拟带宽
                            （说明书注明为单通道工作条件）；
    全功能信号发生器：最高 50 MHz 正弦波输出；
    频谱分析仪：200 kHz～350 MHz，采用 FFT 转换；
    频率响应分析仪（伯德图）：100 Hz～50 MHz；
    显示与操作：7 英寸、1024×600 IPS 电容触摸屏；
    波形采集：最高 50000 wfm/s，支持最高 16-bit 高分辨率模式。

本脚本处理的是该设备导出的私有二进制 .wav 波形，而不是标准 RIFF/PCM
音频 WAV。由于当前尚未从私有文件中可靠解析实际采样率，运行时仍应根据采集
设置通过 --fs 明确指定采样率，不能直接把设备的最高 1 GSa/s 规格当作每次
采集的实际采样率。


1. 文件位置
-----------

脚本：
    .\differential_waveform.py

示波器波形文件可放在脚本当前目录，或通过命令行传入任意文件路径。

建议先在 PowerShell 中进入脚本所在目录：

    cd <脚本所在目录>


2. 安装运行环境
-------------

需要 Python 3，以及 numpy、scipy、matplotlib：

    python -m pip install numpy scipy matplotlib

检查是否安装成功：

    python -c "import numpy, scipy, matplotlib; print('依赖正常')"


3. 最基本的使用方法
-----------------

处理 11.wav，采样率为 1 MHz，使用记录前 4 ms 作为基准，截取 6～8.2 ms，
不使用软件高通滤波：

    python differential_waveform.py 11.wav --fs 1000000 --baseline 0.004 --start 0.006 --end 0.0082 --no-highpass

使用 10 Hz、一阶高通滤波：

    python differential_waveform.py 11.wav --fs 1000000 --baseline 0.004 --start 0.006 --end 0.0082 --highpass 10 --order 1

如不写 --highpass 或 --no-highpass，并且在终端中交互运行，程序会询问是否启用高通；
选择启用后，再输入高通转折频率。


4. 当前信号处理顺序
-----------------

程序当前的处理顺序为：

    1) 读取完整 CH1、CH2 原始数据；
    2) 用原始记录最前面 --baseline 秒的数据，分别计算 CH1、CH2 均值；
    3) 从 CH1、CH2 的全部采样点中分别减去对应均值，完成整体平移；
    4) 按 --start 和 --end 截取需要显示的时间段；
    5) 计算差分：differential = CH1 - CH2；
    6) 如果启用高通，只对已经做完减法的 differential 进行高通滤波；
    7) 如果指定稳态居中区间，再对差分结果进行观察用的中心平移；
    8) 导出 CSV，并生成总览图和局部放大图。

重要说明：

    软件高通不会分别作用于 CH1、CH2，只作用于做差后的差分波形。
    CH1、CH2 图线保持未经过软件高通滤波。


5. 全部命令行参数
----------------

wav
    输入波形文件路径。若文件就在当前目录，可直接写 11.wav。

--fs 数值
    实际采样率，单位 Sa/s。
    私有 WAV 格式不能可靠解析采样率，因此必须填写正确值。

    示例：
        --fs 1000000

    表示 1 MSa/s。

--start 秒数
    输出和绘图的起始时间，相对于整条记录起点。

    示例：
        --start 0.006

    表示从 6 ms 开始。

--end 秒数
    输出和绘图的结束时间，相对于整条记录起点。

    示例：
        --end 0.0082

    表示在 8.2 ms 结束。

--baseline 秒数
    用原始记录最前面多少秒的平均值，分别平移 CH1 和 CH2。
    默认值为 0.004 秒，即前 4 ms。

    示例：
        --baseline 0.004

    该操作让“前 4 ms 的平均值”为零，不保证第一个采样点恰好为零。
    基准计算发生在截取之前，所以即使输出 6～8.2 ms，仍然使用原始记录的前 4 ms。

--highpass 频率
    启用巴特沃斯高通滤波，并设置转折频率，单位 Hz。
    高通只作用于 CH1-CH2 的差分结果。

    示例：
        --highpass 100

--no-highpass
    明确关闭软件高通滤波，并跳过交互询问。

--order 阶数
    高通滤波器阶数，必须为大于等于 1 的整数，默认一阶。

    示例：
        --order 4

--notch [频率]
    启用陷波（notch）滤波，去掉差分信号里的工频干扰。只写 --notch 不给数值时
    默认 50Hz；也可以自己指定频率，比如 60Hz 电网或者其它已知干扰频率。
    和高通一样，陷波也只作用于 CH1-CH2 的差分结果，CH1/CH2 图线不受影响；
    在高通之后进行（如果两者都启用）。

    示例：
        --notch          （等价于 --notch 50）
        --notch 60

--notch-order 阶数
    陷波滤波器阶数，必须是大于等于 2 的偶数，默认 4。
    实现方式是把 2 阶陷波级联 order/2 次（4 阶 = 2 个 2 阶陷波级联），
    级联次数越多，陷波频率处衰减越深，但计算量也越大。

    示例：
        --notch-order 4

--notch-q 数值
    陷波品质因数（notch_hz / -3dB 陷波带宽），默认 30。
    越大陷波越窄，对陷波频率附近的其它信号影响越小；但如果实际工频有漂移
    （比如不是精确的 50.000Hz），Q 太大反而可能陷不干净，需要适当调小。

    示例：
        --notch-q 30

--diff-center-start 秒数
--diff-center-end 秒数
    两个参数必须同时使用。它们指定一段已经进入稳态振荡的时间区间。
    程序使用该区间差分波形的 1% 和 99% 分位值中点估计正弦中心：

        center = (P1 + P99) / 2

    然后从差分波形中减去 center，使最后一行波形便于观察。
    指定的居中区间必须完整位于 --start 和 --end 之间。

    示例：
        --diff-center-start 0.0072 --diff-center-end 0.00815

--volts-per-count 数值
    每个 ADC 码对应的电压。如果不知道，请不要填写，纵轴将使用 ADC counts。

    示例：
        --volts-per-count 0.0000244

-h 或 --help
    显示脚本自带帮助：

        python differential_waveform.py --help


6. 推荐命令
-----------

6.1 当前 AC 耦合数据：不叠加软件高通

    python differential_waveform.py 11.wav --fs 1000000 --baseline 0.004 --start 0.006 --end 0.0082 --no-highpass

6.2 当前 AC 耦合数据：用稳态区间把差分正弦中心移到零，改善观感

    python differential_waveform.py 11.wav --fs 1000000 --baseline 0.004 --start 0.006 --end 0.0082 --diff-center-start 0.0072 --diff-center-end 0.00815 --no-highpass

这条命令推荐用于查看当前 11.wav 的差分波形。

6.3 使用 4 阶、100 Hz 软件高通

    python differential_waveform.py 11.wav --fs 1000000 --baseline 0.004 --start 0.006 --end 0.0082 --highpass 100 --order 4

6.4 按指定参数使用 4 阶、0.1 Hz 高通

    python differential_waveform.py 11.wav --fs 1000000 --baseline 0.004 --start 0.006 --end 0.0082 --highpass 0.1 --order 4

注意：0.1 Hz 对当前只有约 23.5 ms 的记录基本无效，并会显示明显的滤波启动瞬态。

6.5 输入文件不在当前目录时

    python differential_waveform.py ".\waveforms\11.wav" --fs 1000000 --baseline 0.004 --start 0.006 --end 0.0082 --no-highpass

6.6 去掉差分信号里的 50Hz 工频干扰（4 阶陷波）

    python differential_waveform.py 12.wav --fs 1000000 --baseline 0.004 --no-highpass --notch

    等价于 --notch 50 --notch-order 4 --notch-q 30；也可以和高通、稳态居中一起用：

    python differential_waveform.py 12.wav --fs 1000000 --baseline 0.004 --highpass 10 --order 4 --notch 50


7. 输出文件
-----------

脚本在输入 WAV 所在位置附近生成：

    *_differential.csv
        数值数据，包含 time_s、ch1、ch2 和 differential。

    *_differential.png
        三行总览图：CH1、CH2、CH1-CH2。

    *_differential_zoom.png
        开头若干采样点的局部放大图。

如果使用稳态居中，文件名会包含 _centered，CSV 同时包含：

    differential_uncentered
        居中之前的差分，保留原始中心偏移信息。

    differential_centered
        使用稳态区间中心平移后的差分，适合观察交流波形。

如果使用高通，文件名会包含类似：

    _hp100Hz
    _hp0.1Hz

如果使用陷波，文件名会包含类似：

    _notch50Hz

这样不会覆盖未滤波结果，几种滤波可以叠加使用（比如 _hp10Hz_notch50Hz）。


8. 关于高通滤波的重要限制
------------------------

8.1 截止频率必须与记录长度匹配

0.1 Hz 高通的一阶时间常数约为：

    tau = 1 / (2*pi*0.1) ≈ 1.59 秒

当前 11.wav 在 fs=1 MHz 时只有约 23.497 ms，截取部分只有 2.2 ms，远短于 1.59 秒。
因此 0.1 Hz 高通无法在这份数据内进入稳态，也几乎不能消除看到的偏移。

8.2 为什么高通后基线像是在往上移动

脚本使用因果高通滤波。滤波器从零初始状态开始，而截取波形开头通常不为零，
因此会产生启动瞬态。截止频率越低，恢复越慢。短图中看到的可能只是恢复曲线的一小段，
看起来就像基线持续上升或下降。

8.3 AC 耦合已经是高通

示波器选择 AC 耦合时，输入端已经经过硬件高通。软件再加高通属于两级高通级联，
不能恢复已经丢失的直流信息，反而可能使启动瞬态更复杂。

8.4 陷波滤波的注意事项

陷波用 scipy.signal.iirnotch 设计、按 --notch-order/2 级联（默认 4 阶 = 2 节），
同样是因果单次正向滤波，也会有和高通类似的启动瞬态，只是陷波频率通常远高于
记录里的启动瞬态主要能量所在频段，实际影响一般不明显。

--notch-q 决定陷波带宽：Q 越大陷波越窄、越不影响陷波频率附近的其它信号，
但也越要求实际干扰频率和 --notch 指定的频率精确一致。如果电网频率有漂移
（比如不是精确的 50.000Hz），或者干扰本身不是单一频率（比如带谐波），
Q 太大可能陷不干净，可以适当调小 --notch-q（比如 10~20）换取更宽的陷波带。

如果差分信号的真实频率恰好接近陷波频率（比如信号本身就在 50Hz 附近），
陷波会把真实信号也一起衰减掉，这种情况不适合用陷波滤波。

对于当前 AC 耦合数据，建议使用 --no-highpass，并用稳态居中参数改善观察效果。


9. AC 耦合和 DC 耦合的分析区别
----------------------------

AC 耦合：
    适合观察交流成分，但会删除真实直流电平。
    突发信号启动时可能出现基线漂移、下冲或缓慢恢复。
    不适合判断 buffer 的真实固定输出失调电压。

DC 耦合：
    能保留输出的真实直流工作点和失调。
    重新采集时建议 CH1、CH2 都使用相同设置，包括探头倍率、垂直档位、带宽限制和输入阻抗。

使用 DC 耦合重新采集时，如果需要测量真实失调，不应只看平移后的 CH1/CH2；
需要同时保留原始 DC 码值和相应的电压标定信息。


10. 建议的示波器采集设置
----------------------

对于约 500 mV 直流电平上叠加 60～70 mV 小信号：

    耦合方式：DC（测量真实失调时）
    采样模式：确认实际启用 16-bit
    垂直档位：优先尝试 20 mV/div 或 50 mV/div
    垂直 Offset：约 500 mV，使波形位于屏幕中央
    CH1/CH2：使用相同探头倍率、档位、带宽和输入阻抗
    记录长度：同时保留信号启动前和稳定振荡后的数据

使用较小 V/div 前必须确认波形和直流 Offset 不会导致模拟前端削顶。


11. 常见错误
------------

错误：ModuleNotFoundError: No module named 'numpy'

解决：
    python -m pip install numpy scipy matplotlib

错误：请求区间超出记录范围

解决：
    检查 --fs 是否正确，确认 --start/--end 使用的是秒，而不是毫秒数值。
    例如 6 ms 应写 0.006，而不是 6。

错误：高通转折频率必须小于奈奎斯特频率

解决：
    必须满足：0 < highpass < fs/2。

错误：差分居中区间不在输出区间内

解决：
    保证：
        start <= diff-center-start < diff-center-end <= end

警告：自动探测只找到 1 个平滑数据段，怀疑是 DC 耦合下 CH1/CH2 电平接近
      导致通道间隔跳变过小、被合并

说明：
    这不是致命错误，脚本会自动尝试重新拆分（见第 13 节），只是提示性警告。
    拆分后请检查输出图形/CSV，确认两个通道数据在全程（包括记录末尾）都正常，
    没有突兀的毛刺或台阶；如果不理想，需要手动检查 find_smooth_runs /
    split_merged_channel_run 的阈值参数。


12. 当前 11.wav 的推荐结论
------------------------

当前数据是在示波器 AC 耦合下采集，差分中心偏移可能来自：

    示波器 AC 耦合的启动瞬态；
    CH1、CH2 两个通道 AC 高通响应的细微差异；
    buffer 或 MOS 二极管连接负载在大信号下的工作点变化；
    通道增益、零点或探头失配。

当前数据适合观察交流形状和频率，不适合直接判断真实 DC 输出失调。
推荐先使用第 6.2 节的稳态居中命令查看波形；之后改用 DC 耦合重新采集，
再区分固定失调、动态工作点移动和纯交流波形。


13. DC 耦合数据（如 12.wav）：CH1/CH2 自动拆分补救
-------------------------------------------------

背景：

    find_smooth_runs 靠一次跳变（默认阈值 2000 码）把 CH1、CH2 两段数据从
    文件里切开。AC 耦合下这个跳变很可靠，因为示波器为了把两条轨迹分开显示，
    会给 CH1/CH2 加一个几千码量级的人为垂直偏移，通道交界处的跳变足够大。

    换成 DC 耦合后（尤其是 CH1、CH2 都用相近 Offset 居中显示时，参见第 10
    节的建议设置），两个通道真实电平本身很接近，通道交界处的跳变可能远小于
    2000 码，会和真实信号一起被误判成同一个"平滑段"，报错：

        只探测到 1 个平滑数据段，需要至少 2 个（CH1/CH2）

处理方式（load_channels / split_merged_channel_run）：

    脚本探测到只有 1 段时，会在这一大段内部对 find_smooth_runs 本身重新扫
    一遍递减的阈值，收集每个阈值下所有相邻子段之间的间隔。因为 CH1、CH2
    长度基本相等（都约等于整段的一半），真正的通道间隔必然落在整段中间一小
    块区域附近（默认 35%~65%）——只在这块"中央窗口"里找候选间隔，两端（比如
    某个通道内部一次真实信号的大幅跳变/尖峰）不算数。候选间隔里优先选间隔
    最大的（切得最保守，最不容易把间隔数据算进 CH1/CH2）。找到间隔后，直接
    把整段从间隔处切成两半，不要求间隔后半段本身还是一整个"平滑段"——半段
    内部完全可能还有真实信号自己的尖峰，只要间隔位置对了，这些尖峰应该保留
    在对应通道里，而不是被当成还要继续拆分的边界。

    不依赖固定阈值，也不依赖任何硬编码的文件偏移，拆分成功后会打印一行警告
    说明具体切在哪里，供人工核对。

    （最早的版本没有限制搜索范围，直接找全段里跳变最大的一处当间隔；19.wav
    暴露了这个问题——它的 CH2 数据中间有一次真实信号的大幅跳变，比真正的
    通道间隔跳变还大，被误当成了间隔，导致找不到合法的两段划分，报出和
    本节标题相同的 RuntimeError。加上"只在中央窗口找间隔"的限制之后就不会
    再被通道内部的真实瞬态带偏。）

已验证：

    12.wav、19.wav（都是 DC 耦合）用这个补救后都能正常出图/出 CSV，CH1/CH2
    边界和之前 AC 数据（5/8/10/11.wav）的文件内部结构基本吻合，记录中途或
    末尾都没有拆分不准导致的垃圾数据混入波形；11.wav 等 AC 数据的探测结果
    不受影响（阈值 2000 一次就能探测到 2 段，走的还是原来的快速路径）。

    推荐命令（处理 DC 耦合的 wav，先看全程再决定截取区间）：

        python differential_waveform.py 12.wav --fs 1000000 --baseline 0.004 --no-highpass
        python differential_waveform.py 19.wav --fs 1000000 --baseline 0.004 --no-highpass


14. sine_fit_settling.py —— 稳态正弦拟合 / 建立时间测量
-------------------------------------------------------

用途：

    用差分波形里"靠后、已经稳定"的若干个周期拟合出一个标准正弦波
    A*sin(2*pi*f*t+phi)+C，再把这条理想稳态正弦波往前延伸，和实测波形叠加
    对比，直观看出起振后的建立过程，并给出量化的建立时间。

基本用法：

    python sine_fit_settling.py 12_differential.csv --view-start 0.017 --view-end 0.023496 --fit-cycles 3 --tolerance 0.05

参数说明（拟合/分析部分，决定 A/f/phi/C 和建立时间等数值结果）：

    csv             differential_waveform.py 生成的 *_differential.csv
    --view-start/--view-end
                    分析用的时间窗口（秒），默认整份 CSV；决定"自动找拟合
                    周期"和起振/建立时间判定的取值范围
    --fit-cycles    自动模式下，用窗口末尾最后几个完整周期做拟合，默认 3
                    （给了 --fit-window-start/-end 之后这个参数被忽略）
    --fit-window-start/--fit-window-end
                    直接指定用来做 curve_fit 的波形区间（绝对时间，秒），
                    跳过"自动找窗口末尾周期"这一步，比如信号在稳态段内明显
                    分了好几段、想手动挑一段"更干净"的区间时用
    --tolerance     建立时间判据：每周期半幅度和稳态半幅度的相对误差容限，
                    默认 0.05（±5%）
    --column        CSV 里用作差分信号的列名，默认自动选择
                    differential_centered（如果存在）否则 differential
    --no-medfilt    不做单点毛刺中值滤波（默认会用长度 3 的中值滤波去掉该
                    私有格式偶尔出现的孤立掉数尖峰）

参数说明（画图部分，纯显示层面，不影响上面任何拟合数值）：

    --plot-xlim-start/--plot-xlim-end
                    画图显示范围（秒），默认等于 --view-start/-end；可以比
                    分析窗口更窄，用来"裁切"显示范围而不重新拟合
    --x-relative    横轴改成相对 --plot-xlim-start 的时间（ms，从 0 开始），
                    默认用绝对时间（比如原始 10-12.5ms 的窗口裁切后想让横轴
                    显示成 0-2.5ms，就加这个开关）
    --fit-plot-start
                    正弦拟合线/容限带只从这个时刻（绝对时间，秒）开始画，
                    默认等于 --view-start（用来避免拟合线画到还没起振的
                    瞬态段里，产生误导）
    --fit-shift     把正弦拟合线/容限带在时间轴上前移这么多秒（正值=前移/
                    更早出现），只是画图上整体平移曲线，不改变 A/f/phi/C
                    本身（注意单位是秒：如果信号周期在 1ms 量级，传 0.03 会
                    是前移 30ms≈几十个周期，通常是笔误，想要"微调对齐"应该
                    传 0.00003 这种量级，即 0.03ms）
    --vline         在图上画一条竖直参考线（绝对时间，秒），可以重复传
                    多次；传 2 条或以上时会在相邻两条之间标出时间间隔
    --figsize       图尺寸，英寸，格式 宽,高，默认 12,5；4:3 可以传 12,9
    --font-scale    标题/坐标轴/刻度/图例/标注文字整体放大倍数，默认 1.0
    --out-suffix    输出文件名后缀（不含 .png），默认 _sine_fit
    --export-csv    把图上显示范围内的数据（实测值/正弦拟合值/容限带上下界/
                    拟合出的 A 和 f）导出成 CSV，配合 15 节的
                    plot_from_processed_csv.py 可以不重新拟合就画出同一张图

处理流程：

    1) 确定拟合区间：--fit-window-start/-end 给了就直接用；否则在窗口末尾
       找若干个过零点，取最后 --fit-cycles 个完整周期；
    2) 用 scipy.optimize.curve_fit 拟合标准正弦，得到 A、f、phi、C（初始频率
       猜测用拟合区间内实际过零点的间距估计，不是简单地拿区间总长度除
       --fit-cycles——区间和真实周期数对不上时会给出一个偏差很大的初始值，
       curve_fit 可能收敛到错误的局部解）；
    3) 用整条记录里公认安静的一段估计基线噪声水平，找首次明显偏离基线的
       采样点作为"起振时刻"（不能用窗口本身估计噪声，因为 --view-start
       往往已经晚于起振点，会把起振瞬态也算进"基线"）；
    4) 用拟合出的 C 做零点，逐周期计算实测半幅度和拟合稳态幅度 |A| 的比值，
       找到"从此以后所有周期都落在 ±tolerance 容限带内"最早的周期，作为
       建立时间；
    5) 画图：测量曲线按 --plot-xlim-start/-end 裁切显示范围，正弦拟合线/
       容限带只在 --fit-plot-start 之后画出（--fit-shift 不为 0 时先整体
       平移），有 --vline 就叠加竖直参考线和间隔标注。

输出：

    <csv 同名前缀><out-suffix>.png（--out-suffix 默认 _sine_fit）
        实测波形（绿色实线）+ 延伸后的理想正弦波（红色虚线）+ ±tolerance
        容限带（浅红色）+（可选）竖直参考线和间隔标注。

    终端打印拟合参数（含标准误差）、拟合残差、起振时刻、逐周期幅度比例表、
    建立时间。

    （--export-csv 给了的话）额外输出处理后的 CSV，见第 15 节。

关于 12.wav 的结果（2026-08-12）：

    频率 f ≈ 1615.5 Hz（周期 ≈ 0.619 ms），幅度 A ≈ 547.4 ADC counts（未定标）。
    起振时刻 ≈ 17.266 ms，进入并保持 ±5% 容限带的时刻 ≈ 17.794 ms，
    建立时间 ≈ 0.528 ms（约 0.85 个周期）。

裁切/标注示例（14_hp200Hz.wav，2026-08-15）：

    只显示 10-12.5ms（横轴改标成 0-2.5ms），正弦拟合线/容限带只从 10.5ms
    开始画，容限 ±10%，另外在 10.49ms 和 10.76ms 处画竖直参考线并标出间隔，
    图改成 4:3、文字放大 1.3 倍：

        python sine_fit_settling.py 14_hp200Hz_differential.csv \
            --view-start 0.010 --view-end 0.015 --tolerance 0.10 \
            --plot-xlim-start 0.010 --plot-xlim-end 0.0125 --x-relative \
            --fit-plot-start 0.0105 --vline 0.01049 --vline 0.01076 \
            --figsize 12,9 --font-scale 1.3 \
            --out-suffix _sine_fit_cropped

    如果想手动指定拟合用哪一段波形（而不是自动挑窗口末尾最后几个周期），
    比如相对新坐标轴 3-5ms（也就是绝对时间 13-15ms）：

        python sine_fit_settling.py 14_hp200Hz_differential.csv \
            --view-start 0.010 --view-end 0.015 --tolerance 0.10 \
            --plot-xlim-start 0.010 --plot-xlim-end 0.0125 --x-relative \
            --fit-plot-start 0.0105 --fit-window-start 0.013 --fit-window-end 0.015 \
            --out-suffix _sine_fit_fitwin13-15ms

注意事项：

    实测波形本身有约 ±4~5% 的周期间幅度起伏（可能是真实谐波成分或探头/耦合
    噪声，不是单纯的建立过程），这基本是这份数据能给出的精度极限——容限
    收得比 ±5% 更紧（比如 ±2%），稳态段自己都持续满足不了，测出来的"建立
    时间"没有意义。

    输出的幅度单位和 --volts-per-count 一致：不加这个参数就是 ADC counts，
    加了就是伏特，用法参见第 5 节。

    --plot-xlim-*/--x-relative/--fit-plot-start/--fit-shift/--vline/--figsize/
    --font-scale 这些都是纯画图参数，默认值等于原来的行为，不传的话和没加
    这些功能之前生成的图完全一样；--fit-window-start/-end 不传的话也还是走
    原来"自动找窗口末尾周期"那条路径。


15. plot_from_processed_csv.py —— 从已处理的 CSV 直接重画同一张图
-------------------------------------------------------------------

用途：

    配合 sine_fit_settling.py 的 --export-csv：先用 sine_fit_settling.py 把
    某次拟合+裁切的结果（实测曲线、正弦拟合曲线、容限带上下界、拟合出的
    A/f、拟合线起画时刻）导出成一份"处理后"的 CSV，以后要反复重画同一张图
    （比如只是调配色、加标注）时，就不用每次都重新读原始 *_differential.csv
    再跑一遍 scipy.optimize.curve_fit——本脚本不依赖 scipy，只是把 CSV 里
    已经算好的数字按原来的样式画出来。

    确定参数、想固化成"最终版"结果时适合用这条路径；如果还要改
    --tolerance/--fit-plot-start/--fit-shift/--fit-window-start 等拟合/取值
    参数，仍然要回到 sine_fit_settling.py 重新导出一次 CSV，本脚本本身不
    认这些参数。

基本用法（两步）：

    第一步，用 sine_fit_settling.py 正常出图，同时加 --export-csv 导出数据：

        python sine_fit_settling.py 14_hp200Hz_differential.csv \
            --view-start 0.010 --view-end 0.015 --tolerance 0.10 \
            --plot-xlim-start 0.010 --plot-xlim-end 0.0125 --x-relative \
            --fit-plot-start 0.0105 \
            --export-csv 14_hp200Hz_differential_cropped_processed.csv

    第二步，用这份 CSV 重新画图（比如换台机器、或者不想重新装 scipy）：

        python plot_from_processed_csv.py 14_hp200Hz_differential_cropped_processed.csv

参数说明：

    csv       sine_fit_settling.py --export-csv 导出的处理后 CSV
    --out     输出 PNG 路径，默认 <csv 同名前缀>.png

CSV 列说明：

    time_ms             画图用的时间轴（ms），已经是 --plot-xlim-*/--x-relative
                        处理过的结果
    measured_mV         实测差分电压（对应绿色实线）
    sine_fit_mV         稳态正弦拟合曲线在该时刻的值（对应红色虚线，已经应用
                        过 --fit-shift）
    tol_lower_mV/tol_upper_mV
                        ±tolerance 容限带上下界（对应浅红色阴影）
    fit_A_mV/fit_f_Hz    拟合出的幅度/频率，每行重复，用来拼图例文字
    fit_plot_start_ms   正弦拟合线/容限带从哪个时刻开始画，之前的时间点该行
                        sine_fit_mV/tol_*_mV 仍然有数值，但重画时会被忽略

输出：

    <csv 同名前缀>.png（或 --out 指定的路径），样式和
    sine_fit_settling.py 直接生成的图一致（同样的配色、线型、图例格式）。

    注意：CSV 里没有存 --vline/--figsize/--font-scale 这些纯画图开关的设置，
    如果原图加了竖直参考线/自定义尺寸/放大字体，重画出来的图不会带上，需要
    的话在 plot_from_processed_csv.py 里照着 sine_fit_settling.py 的画法自己
    加。


16. differential_waveform_fft.py —— 差分波形 FFT 图
----------------------------------------------------

用途：

    完整复用 differential_waveform.py 原有的 WAV 解析、基线平移、CH1-CH2、
    高通/陷波和稳态居中处理，然后对最终差分结果做傅里叶变换，额外输出单边
    幅度频谱图。原脚本保持不变，需要 FFT 时改用这个新入口。

基本用法：

    python differential_waveform_fft.py 14.wav --fs 500000 --baseline 0.004 --no-highpass

只把 FFT 图显示到 5 kHz（不改变 FFT 计算本身）：

    python differential_waveform_fft.py 14.wav --fs 500000 --baseline 0.004 --no-highpass --fft-max-frequency 5000

FFT 处理顺序：

    1) 运行 differential_waveform.py 并生成原有 CSV/总览图/局部放大图；
    2) 有 differential_centered 列时优先使用，否则使用 differential；
    3) FFT 前减去差分信号均值，去掉直流分量；
    4) 加 Hann 窗以降低有限记录造成的频谱泄漏；
    5) 按 Hann 窗 coherent gain 修正并转换成单边峰值幅度谱；
    6) 标出当前显示范围内的最大频谱峰值和对应频率。

新增参数：

    --fft-max-frequency Hz
        FFT 图的横轴上限。默认显示到奈奎斯特频率 fs/2；如果指定值超过 fs/2，
        会自动裁剪到 fs/2。该参数只影响显示范围，不影响 FFT 数据和主流程。

新增输出：

    *_differential_fft.png
        最终差分信号的 FFT 单边幅度频谱图。纵轴幅度单位与差分 CSV 一致：
        未指定 --volts-per-count 时是 ADC counts，指定后是 V。
