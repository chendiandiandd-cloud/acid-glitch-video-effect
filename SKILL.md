---
name: acid-glitch-video-effect
description: 参考驱动酸性故障与复古印刷离线视频处理，提供自包含CLI、五类背景配方、42帧全画面自然色回闪、人物软边合成与已有轻量多人ONNX缓存。适用于上传视频效果处理、全片或指定时段渲染、Skill调优；单次顺序解码、有限前瞻保持锚点插值，默认一次渲染直接交付、不追加质检或报告，不用生成模型、不创建工作台。跨素材适配仍是策略，不宣称完整复刻或所有类型已验证。
author: "chenyanqi.1008"
---

# 酸性故障 · 离线处理

## 默认执行链
读取必要输入信息 → 一次正式渲染（其中按需复用/生成人物锚点缓存）→ FFmpeg正常退出并原子发布 → 直接交付。无渲染后质检轮次或报告。

- 用户要求处理视频本身即授权该范围内处理及必要轻量人物分割，不重复索要生成授权；新增语义模型、付费或公开外发另确认范围。禁止图像/视频/音乐生成模型，不创建网站或工作台。
- 不默认先出4秒/6秒预览。测试按本次明确长度；仅编辑/审查不出视频、不重新分割。旧“每次优化必出测试片”约定已取消，不沿用最近素材自动补片。
- 默认不读取全部参考/截图、不额外抽接触表、不反复分析对照或试渲染、不跑全套单元测试、不完整播放或重复全片解码。仅参数缺失、输入异常或明确开发/调试任务时补必要步骤。
- 使用固定[完整入口](scripts/render_video.py)，必填input/output，省略duration处理全片（start非零则处理剩余全片），没有4/6秒限制。入口自身解析包内路径，可从任意cwd以绝对脚本路径调用。
- 入口一次ffprobe元数据检查加压缩包PTS审计（demux、不解码），拒绝VFR/non-grid PTS、非方形SAR、HDR与非直角旋转；CFR源PTS持续推进，效果时钟默认repeat。保留[独立预检工具](scripts/inspect_video.py)的metadata-only模式供仅审查时使用，不默认重复调用。
- 输出真MP4/H.264，保留显示宽高与fps；偶数尺寸yuv420p，奇数尺寸yuv444p不缩放/补边/裁切（部分播放器兼容性较低）。音频兼容时copy，否则AAC；无音轨不添音乐。不再对输出运行ffprobe、二次duration比对、音包校验或全片解码；正常退出后直接交付。已有输出默认报错，显式overwrite才覆盖，始终禁止覆盖输入。

运行基线为CPython 3.11（已测Linux x86_64）；使用独立venv后执行 `python3 -m pip install -r requirements.txt` 安装[锁定依赖](requirements.txt)。其他Python版本（含3.13+）不在此锁定组合支持范围；其他OS/架构需确认原生wheel/库可用，不宣称手机本机支持。系统FFmpeg/ffprobe>=5（含libx264）必须另装并加入PATH，pip不提供；入口仅做轻量依赖缺失/版本护栏，不自动安装、替换系统或增加质检轮次。已有[人物权重及校验](models/README.md)随包，不自动下载。
```bash
python3 -B scripts/render_video.py --input /absolute/input.mp4 --output /absolute/output.mp4
python3 -B scripts/render_video.py --input /absolute/input.mp4 --output /absolute/range.mp4 --start 10 --duration 12
```
默认segmentation auto复用有效缓存，缺锚点用既有轻量人物模型；cache-only禁止新推理；明确无需人物mask时用none（不是检测无人）。可指定model/cache-dir，缓存默认系统临时目录。stdout默认只返回一行output路径JSON，不构建/写盘统计或质检报告；显式--diagnostics仅复用渲染中已有便宜计数/耗时输出开发JSON，不增加输出探测或解码。非帧栅格时段按区间内源PTS选帧，实际起止及帧量化时长仅在diagnostics中提供；不循环源画面。

## 风格与时间硬约束
- 黄黑实块优先，窄中间调网点、细碎锐利断墨/划痕/稀疏白点；避免整脸砂纸、乳白云雾/霉斑。磨损随内容运动，印刷/故障可跳动，不全锁屏或全机械光流平移。
- 背景五状态：source原景、duotone双色、ink_colorfield墨块叠彩色场、liquid_replace大范围二维液化替换、horizontal_glitch局部横拉切裂。建筑不是永久保护对象，状态可分区共存，不机械均匀轮换。
- 液化先组织不规则折叠/回卷/分叉和深墨，再有限主色大色区；禁止整套HSV彩虹、等距霓虹细带、发光描边和整屏随机RGB。不以全景降饱和替代设计；艺术横断不同于固定高度mask接缝。
- [时间配置](references/reference-profile.json)：参考42帧/8fps/5.25秒，无音轨。F00自然基准；F02/F14/F17/F34/F38/F41整画面复色，各观测格0.125秒；F06/F22/F25/F29仅局部回归。高fps按PTS采样，不只插一帧；低fps漏采注明限制，不改fps/脉宽。
- 用 [时间查表](scripts/reference_timeline.py) 在[0,5.25)选truncate，超过5.25秒选repeat：只repeat效果时钟，源PTS持续推进。长片循环是适配推断，不是参考事实。
- strong/natural均来自当前PTS完整画面；顶层whole-frame gate同时复色人物/近景/背景，gate后不再叠强黄黑。背景source仍可保持黄黑人物，不能冒充整画面回闪。

## 区域与人物规则
- 主体S、近景N、可编辑E、保护P、染色T、印刷I分别定义；E不自动等于1-person mask，I不限人物。保护保辨识和关键文字，不禁止自然gate复色。
- 多人取全部实例并集，包括远处/边缘小人。可靠且alpha=1核心保留认可印刷基准；软边用独立人物印刷层与新背景alpha合成，不冻结混旧背景的非零支撑，不膨胀厚壳/整片模糊。
- 缓存不因颜色/做旧/节奏调参失效；源、模型、分割配置、几何或时序变化才检查失效。快运动、新露出、遮挡及切镜按需更新；切镜清空间/光流历史，默认不重置全局效果时钟。
- 无人物/无天空允许；动物、产品、风景、室内、动画、屏录按区域策略处理，未经授权不引入非人语义模型。候选不可靠则受限印刷/染色/形变并注明风险，不冒称准确分割或已验证泛化。

## 包内实装与按需资源
| 内容 | 实际边界 / 何时加载 |
| --- | --- |
| [背景配方](scripts/reference_background_recipes.py) / [状态选择](scripts/background_print_states.py) | NumPy数组双色、墨填色、宽带二维回卷/分叉、当前印刷结构局部横断；无识别、状态时钟或编码 |
| [人物合成](scripts/matte_composite.py) | 核心保护、软边混新层、完整natural优先；不检测/细化mask |
| [区域工具](scripts/background_regions.py) / [旧保护采样](scripts/background_structure.py) | 显式范围、mask接缝诊断、有界采样；旧P>0冻结只用于无污染基准，不修软边 |
| [数组指标](scripts/quality_metrics.py) | 全人物mask合并、泄漏/覆盖、缓存键与实测参数耗时估算；不管理缓存、不打美学分 |
| [实现/开发](references/implementation.md) | 完整链来源、缓存/PTS/有限前瞻契约、实测验证和限制；仅接入/调试时读 |
| [跨素材策略](references/adaptation.md) | 新类型、复杂运动/曝光/几何时读；不是已验证的自动路由 |
| [视觉证据](references/visual-spec.md) / [背景专项](references/background-structure.md) | 用户要求复核参考或调风格时读，不默认重新审计 |
| [图片映射](references/approved-image-guide.md) / [参考板](assets/reference-images/approved-board.png) | 视觉开发按需；6图5来源页，建筑强匹配缺口仍在 |
| [专项验收](references/acceptance.md) | 用户明确视觉评审/开发调试时读；数值通过不代表视觉通过 |

所有有效测试脚本与参考资产保留原位，仅按需开发/调试加载执行。包内已有完整可移植运行链，当前美学仍为既有实验基准，不承诺整体视觉认可、完整复刻或全部素材类型已验证。
仅在AIME等支持草稿/空间同步机制的宿主中：修改只在本地草稿生效，草稿暂停空间自动同步，上传或废弃退出后恢复；其他平台按各自管理机制执行。仅用户明确要求才上传。相对路径/命令以本Skill根目录为基准。
