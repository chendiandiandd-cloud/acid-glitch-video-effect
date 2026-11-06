# 完整离线链：接口与限制

仅工程接入/调试时读取；正常处理直接运行SKILL.md固定命令，不默认试片或回归。

## 入口与依赖

`python3 -B scripts/render_video.py --input /absolute/input.mp4 --output /absolute/output.mp4`

- 必填input/output；start默认0，duration省略为剩余全片，无4/6秒限制。
- segmentation默认auto（缓存不足时使用已有轻量人物模型），cache-only禁止推理，none是明确零人物mask策略，不是语义无人检测。
- model默认包内路径；cache-dir默认系统临时目录acid-mask-cache。默认禁止覆盖输出，overwrite显式开启，不能覆盖输入或输入硬链接。
- 支持/已验证基线为CPython 3.11、Linux x86_64；其他Python版本（含3.13+）不在当前锁定组合支持范围，不能把旧Python>=3.10理解为所有新版本兼容。NumPy==1.26.4、opencv-python-headless==4.11.0.86、onnxruntime==1.16.3见[requirements](../requirements.txt)。其他OS/架构未做集成验证，须确认原生wheel及系统库支持，不宣称Android/iOS本机可用。
- 在Skill根目录用 `python3.11 -m venv /path/to/venv` 后，执行 `/path/to/venv/bin/python -m pip install -r requirements.txt`。系统FFmpeg/ffprobe>=5（含libx264）需另装并加入PATH，pip不提供，不自动安装/替换系统。包内[已有权重](../models/README.md)13,681,633字节及SHA-256均已记录，不自动下载。
- [轻量启动护栏](../scripts/runtime_dependencies.py)在native import前检查Python/基础包锁定版本；真实人物模型创建前再检查ORT，避免旧ORT+NumPy2 ABI崩溃。缺包、native库加载错误、缺FFmpeg给安装指引；只查metadata/PATH，不执行环境完整质检、不探测二进制版本、不写报告。none/cache命中仍不导入ORT。
- 整包scripts/references/models可复制到任意路径，从任意cwd执行绝对脚本路径；无需工作区scripts或其他Skill。无inner_skills资源打包。

## 迁移来源（2026-11-06）

| 包内文件 | 原工作区来源与处理 |
|---|---|
| [render_video.py](../scripts/render_video.py) | scripts/render_acid_print_states_4s.py的编码/封装，去掉实验授权flag、硬编码素材、4/6秒上限、预算预估、调试图输出 |
| [acid_renderer.py](../scripts/acid_renderer.py) | 同一最新入口的印刷/磨损/当前PTS自然分支；ink_print来自scripts/render_acid_flash_4s.py，仅提取真正使用的函数，不保留旧CLI |
| [acid_test_io.py](../scripts/acid_test_io.py) | scripts/acid_test_io.py的源/缓存/切镜适配，改为压缩包PTS预检和单次解码有限前瞻 |
| [acid_matte_ink_algorithms.py](../scripts/acid_matte_ink_algorithms.py) | scripts/acid_matte_ink_algorithms.py的alpha细化、直接锚点光流及一致性插值，公式不变 |
| [person_instance_mask.py](../scripts/person_instance_mask.py) | scripts/person_instance_mask.py原Kalray raw-head解析与多人并集，仅路径独立与按需导入 |
| [reference_background_recipes.py](../scripts/reference_background_recipes.py) | 已有包内五状态，按state懒算，不改颜色/墨层/随机粒度 |

实际import闭包：上述模块，以及包内reference_timeline、background_print_states、matte_composite和标准库/requirements依赖；不穿透调用工作区或平台内部脚本。

## PTS、几何、编码

预检只用ffprobe流/格式元数据和压缩packet PTS（demux，不调用show_frames，不视频解码）。按time_base排序检查单包单帧的CFR栅格与唯一PTS。支持该契约的CFR输入；VFR/non-grid PTS明确拒绝，不声称VFR支持。压缩PTS列表占O(帧数)的小型元数据内存；不保留全片raw或gray/mask序列。

当前源PTS持续推进；仅参考效果时钟repeat，切镜不重置时钟。start非零时选取[start,start+duration)内的源帧，音频从首选帧时间开始；输出从0开始，时长为选帧数/fps。非栅格区间量化到帧，实际首末PTS及video_seconds仅在显式--diagnostics的stdout中提供，默认不构建或写盘报告。此时磨损/RNG从本次区间首帧初始化，不宣称等于先渲染全片再裁切的磨损历史。

沿用FFmpeg自动直角旋转及显示宽高交换。SAR须1:1，HDR/任意角度旋转不自动转换，最短边>=4像素。偶数native尺寸输出H264/yuv420p；奇数native尺寸H264/yuv444p，不缩放/补边/裁切，部分硬件播放器不支持4:4:4。输入高位深SDR依旧按原路径变成8bit BGR处理，不宣称高位深保真。

编码输入是处理后BGR帧；有音轨时才打开第二路原输入并仅map音轨，属于音频demux，不是视频decode；无音轨不重复打开源。兼容MP4音频copy，否则AAC；无音轨不添加音频。渲染结束只检查decoder/encoder/mux进程exit，不再ffprobe输出、不二次duration比对、不做音包校验或全片解码，即使--diagnostics也不追加这些调用。临时输出在目标目录受管理的.acid-render目录，正常退出才原子发布；异常杀进程、回收pipe并清临时目录，既有输出不被错误运行破坏。

## 单次解码与像素契约

- 一个顺序FFmpeg视频decoder；在线灰度变化/HSV hist切镜阈值保持原算法。8Hz锚点加切镜锚点，与原采样规则一致。
- 仅缓冲当前锚点到下一锚点的帧（约0.125秒，含右锚点）；切镜增加锚点并终止跨镜插值；最后尾段使用左锚点。与旧预解码后双锚点插值语义一致，不偷换为单边递归mask。
- cut清mask/flow/磨损历史；anchor灰度与紧凑mask仅保留左右两个锚点。lookahead_peak_frames是帧队列峰值，另有固定数量当前帧、两个锚点与工作数组；不是全片缓存。
- natural提前跳过person print、alpha refine/direct anchor flow和背景build；legacy confidence、wear flow、切镜、RNG消费、tick/时序历史仍正常推进。strong帧只计算所需state；未使用的自然分支也不额外算。
- 背景fluid按需生成；source/duotone不生成fluid，duotone不算fill，liquid不算duo/fill，glitch只算必要fill。背景局部独立seed/RNG仍产生同样flecks/rectangles，允许同tick多state调用，不断历史。

## 缓存合约

缓存v3含源文件流式SHA-256、模型SHA-256、display/mask geometry、旋转策略、fps、时间coverage及原detail/long960/8Hz/hist切镜配置。颜色/印刷/回闪调参不纳入分割键；两个视频不会混用。覆盖区间不同按保守独立命名空间处理，不复用旧v2实验缓存（旧键含全PTS列表，契约不同）。

模型/源fingerprint各流式计算一次并用于同一manifest/cache key，不另跑整文件SHA校验，不把视频字节全装内存。锚点缓存uint8紧凑mask验证shape/dtype，manifest完全比对，损坏或不匹配明确报错；写mask临时文件后原子rename。cache-only缺mask报错，不偷做推理；none不读模型或缓存、不导入ONNXRuntime。

## 实测验证边界

2026-11-06迁移基线开发测试只使用临时合成微媒体或数组，不渲染用户视频、不做新分割推理；该阶段使用既有合成mask缓存验证24fps CLI和光流，未测试真实人物模型性能/精度。随后依赖修复验证另述如下。

7秒、64×48、8fps无音轨合成视频：56帧，video_decode_passes=1，frames_decoded=56，wear_flow_calls=55；natural=9，person_print从56降到47，强分支跳过9。背景调用source=5、duotone=11、ink_colorfield=9、horizontal_glitch=8、liquid_replace=14，共47（off为56）。优化on/off处理帧与实际H264解码帧逐像素相等，差异0。独立eager背景oracle也逐像素相等，并验证每state只算所需底层配方。合成非零mask/运动/切镜的24fps数组验证有限前瞻与预解码双锚点oracle相等。

便宜计数/阶段时钟沿用已有实现，不触发额外媒体计算。仅显式--diagnostics构建stdout统计JSON（preflight/cache setup/decode read/cut detection/segmentation/effects/encode write/finalize/total时间，解码pass/帧数、cache hit/miss、推理/flow/print/跳过次数及state调用）；默认只返回output路径，不构建统计报告，不写report/stats文件，已删除output_probe_seconds及整个输出探测。阶段墙时包含pipe等待/并行重叠，不能简单求和当纯CPU成本；frames_decoded计交给Python的帧，input seek内部keyframe preroll不可观察。小媒体计时不用于承诺用户素材速度倍数，未测速或重渲染用户素材。

迁移基线曾通过包内110项测试与工作区10项无媒体回归；迁移开发回归执行包内测试120项（原110项＋[默认路径/异常清理契约](../scripts/test_render_runtime.py)10项），quick_validate通过。新契约用64×48、8fps、0.5秒临时合成媒体证明：输入ffprobe两次（metadata/视频PTS），output postprobe=0、decoder=1、encoder/mux=1；默认不构建统计报告、不写JSON/JPG；diagnostics不追加媒体检查，auto有效缓存源/模型各hash一次且零推理；失败保留原错误、回收进程/pipe/临时目录且不破坏已有输出。24fps/1秒开发CLI仍使用8个合成mask缓存，cache_hit=8、cache_miss=0、model_inferences=0，frames_decoded=24、wear_flow_calls=23、anchor_flow_samples=22、lookahead_peak_frames=4。

## 依赖修复验证（2026-11-06）

新建隔离venv（不继承system site-packages），CPython 3.11.15/Linux x86_64，从公开PyPI按requirements安装三项固定主依赖，pip check通过。沿用系统/usr/bin/ffmpeg及ffprobe 5.1.9（libx264），不是pip或venv自动提供。PersonInstanceMask对合成零数组执行detail真实推理成功；64×48、24fps、0.5秒无音轨合成视频完整auto CLI正常退出，12帧、cache_hit=0、cache_miss=4、model_inferences=4（detail每锚点3次forward）。无人物合成mask为零仅证明模型加载/运行，不证明人物精度或全素材美学。

复用旧隔离venv的NumPy2.2.6/OpenCV4.12.0.88/ORT1.16.3坏组合：修复后CLI退出1并给ABI/安装指引，未import numpy/cv2/ORT、未创建native session、无segfault。缺基础包及缺系统FFmpeg给单行友好错误。开发验证通过[依赖护栏单测](../scripts/test_runtime_dependencies.py)9项、默认路径/cleanup单测10项、入口/数组/portable单测18项，共37项；quick_validate及git diff --check通过。默认仍单次渲染、无自动preview/输出质检/报告；模型/视觉算法不改。外部手机平台的仓库读取安装失败仍无原始日志，不能由该运行时修复认定根因或承诺解决。

## 按需开发测试

包内测试按需执行：`python3 -B -m unittest discover -s scripts -p 'test_*.py' -v`。测试覆盖任意cwd/复制独立包、默认全片>6秒、start/duration、有/无音轨、copy/AAC、奇数尺寸、旋转/CFR、明确拒绝VFR、模型/缓存错误、none、FFmpeg失败cleanup、覆盖护栏。数值通过不代表整体美学或全部素材类型验证；全部参考资产和既有测试保留。
