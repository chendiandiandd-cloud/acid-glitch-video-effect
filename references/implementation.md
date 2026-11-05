# 合成实现与性能：背景状态、人物保护、整画面回闪

## 能力与失败边界
当前没有获用户整体认可的完整renderer。人物局部被认可，背景结构染色/形变测试仍不符合预期；不复制独立实验脚本为生产入口。随包工具包含预检、区域指标、时间控制、保护采样、背景数组状态及真实宽带回卷/局部横断配方，不包含完整识别/MP4流水线。reference_background_recipes.py无视频/缓存路径，2026-11-05从工作区旋回思路重新提炼；实验renderer已直接调用它，人物内部/alpha处理、RNG与自然gate不改。

当前用户明确要求每次优化后交付一条新4秒测试片：先改文档/参数/代码并做数值回归，再用当前/最近指定素材出片，优先复用已认可缓存。只有用户明确暂停、只改不出片或撤回授权才不抽取/渲染媒体。持续约定不授权新模型、付费生成、批量出片或无限重试。

## 三种数据与三个控制
数据：当前源PTS、参考效果时间、每镜头空间区域。源帧和人物运动不被效果时钟替换；切镜只重建空间，默认不重置效果时间。

控制：背景state（五类）、允许近景N的处理状态、whole-frame natural_gate。背景source恢复原景不会自动开启自然gate，也不取消人物黄黑；真正整画面gate才令人物/背景/近景共同复色。

## 合成顺序
1. 从当前源帧提取背景亮度墨层/色场候选，确定允许编辑E；保留人物印刷参数与可靠内部基准，用户否定的mask/软边允许修正，基准不得冒充无背景污染的独立人物层。
2. 背景按区域选择source、duotone、ink_colorfield、liquid_replace、horizontal_glitch；细节见background-structure.md。
3. 先组织背景的深墨/亮块、填色或替换大形，再加该层细密颗粒、过渡网点和断墨；不把人物再次送入新背景处理。
4. 当前人物边缘修复使用 `matte_background_composite`：仅可靠且alpha=1的核心复用baseline；软边以独立人物印刷层与新背景alpha合成，不混旧baseline背景。旧 `protected_background_composite` 的P>0冻结契约保留为严格背景-only工具，不用于修复被用户否定的软边。natural_gate整画面选当前完整自然分支。
5. gate之后不套强黄黑/彩色层。人物保护不是禁止已认可自然分支复色，不重放/冻结当前输入。

## 五类数组分支
`background_print_states.py`定义背景状态接口，传入RGB/BGR顺序、源帧、墨/亮配色、窄阈值过渡和可选网点/色场。配色、阈值与粒径为待校准参数，不是参考测量。

- source：返回当前源背景；可在调用侧加入经校准的轻微残余断墨。人物仍用强处理baseline。
- duotone：原亮度阈值转深墨/亮块，无网点时硬阈值，有网点时只在窄中间调区组织二值点，不保留摄影渐变。
- ink_colorfield：同一墨结构压在彩色填充之上，暗墨稳态不被色场污染。填色可有液化/彩噪，但不是整块建筑摄影染色。
- liquid_replace：必须显式提供液化帧，允许背景建筑消失，不自动混原图；液化场可用同包reference_background_recipes生成；大形/运动仍需单独视觉对照。
- horizontal_glitch：必须显式提供故障帧，不能无声退回普通染色；调用者组织横向拉伸/条带断裂/块状错位，不用整屏RGB雪花替代。

五类不是完整render入口，不识别建筑，不生成视频或状态时间表。墨区判断由源结构驱动，具体艺术效果仍待校准。

`background_structure.py`保留有界源采样工具；只在需要源结构的故障/局部变形使用，不要求liquid_replace保留建筑。采样越界、落在人物/非法E时回退，无wraparound。最近邻只证明逻辑，最终插值也必须做保护检查。

## 时间控制：不修改既有42格
reference-profile.json仍只保存审计的natural/partial/strong分类，不伪填五类state。F00基准、F02/14/17/34/38/41回闪；每个交付观测格0.125秒，截图文件时间不提供这些状态的PTS。

从Skill根目录执行：
```bash
python3 -B scripts/reference_timeline.py --profile references/reference-profile.json --pts 0.25 --extension truncate
python3 -B scripts/reference_timeline.py --profile references/reference-profile.json --pts 10.75 --extension repeat
```

truncate仅[0,5.25)，越界报错；repeat仅循环效果查表，源PTS保持推进，超参考范围标记推断。长片段落映射未实现，不写不存在的选项。不固定0.5秒轮换、不假设音频卡点；参考无音轨。

30/60fps按真实PTS采样0.125秒脉冲，不替换成一个输出帧；低fps/VFR可能漏事件，记录限制，不自行延长脉冲或升fps。原参考8fps不证明人物原始制作帧率。

## 模型与区域缓存
已授权轻量模型仅用于人物检测/分割；多人mask取并集，禁止只保留最大实例。模型导出头/类别/letterbox/mask格式按实际版本确认；非人主体传统候选路线，新增语义模型先授权。区域策略见adaptation.md，无天空不视为无E。

人物缓存键含源指纹、模型版本、分割配置、旋转/输出几何/采样时刻；不含背景颜色、做旧、节奏。调背景复用已认可人物缓存，背景墨层/区域/网格独立缓存。

关键帧8–12Hz+传统光流是性能起点，不保证快速运动质量。新露出/遮挡/前后不一致触发更新，切镜清历史。曝光按镜头校准且背景单独使用，不能为背景改人物共用阈值。HDR先明确色彩变换，不把HDR当8位亮度。

## 性能、格式与测试
有授权时FFmpeg pipe单次解码/编码，NumPy/OpenCV批处理，预计算网格/复用缓冲，模型只准备一次、线程有界。当前源人物仍连续运动，不因背景8Hz更新而冻结人物。

抽样估算只在生成授权下进行；冷启动/分割/合成/编码分开测。超预算先优化，降低清晰度/fps或截短须确认。此前12.7秒输入约259秒处理是效率反例，不是快速承诺。

输出真MP4/H.264，保留约定长度、显示比例与源音轨；兼容时复制音频否则AAC，检查包边界时长、音画同步与旋转。无音轨不添音乐，不发布网站。

单元测试只用合成数组证明分支/墨区/保护/回闪路由。它们不证明网点尺度、液化/故障形态、建筑识别、动态节奏或完整复刻；实际视觉验收仍需原参考对照与完整播放。

## 数组接口的准确调用约定
```python
background_state(
    source_frame, state, *,
    color_order, dark_color, light_color,
    threshold=.5, transition_width=.08,
    halftone=None, color_field=None,
    liquid_frame=None, glitch_frame=None
)
```
源/场/替换帧统一uint8 H×W×3，color_order显式RGB或BGR；配色为该顺序的0..255整数三元组，没有默认配色。transition_width是阈值两侧窗口总宽，halftone为同尺寸H×W的0..1点阵。默认阈值/窗口为实验起点，不是参考测量；编码通道Rec.709加权值不是线性光亮度。所有参数检查有限性/形状/类型/范围，输入不原地修改。

状态工具不接收PTS或安排时间；liquid_replace/horizontal_glitch只选择调用者生成的对应帧并检查，不代表液化场或故障场已实现。用同一当前PTS的源与场，经保护合成后再选整画面自然分支。

## 可编辑区域工具的接入
`background_regions.py` 无模型/媒体/时钟依赖，需NumPy。当前保护mask建立后，用 `editable_background_region(protected_mask, policy='full_background')` 显式处理完整非保护背景；需要内容限定范围时用 `policy='explicit', allowed_mask=...`。P任何非零值均排除，不能阈值到0.5后丢失软边保护。随后传入既有 `protected_background_composite`，最终仍由whole-frame gate路由自然分支。

全背景处理范围不同于语义分割，且不能与allowed_mask混用；explicit要求有效同尺寸允许mask，非法输入报错。不从全背景政策推导近景、文字或产品可任意破坏。

`horizontal_cut_rows(region, min_span=.8, min_step=.75)` 的默认值是诊断起点，不是参考测量；报告相邻行绝对权重差达到阈值、跨宽度比例达到阈值的行。检查的是mask而非背景图像，避免误伤艺术横断。单行/空异常、uint8下溢、NaN/Inf、错形状、输入变异由区域测试覆盖；它不是视觉质量评分或语义识别器。

## 独立实验的本轮落地边界
工作区五类背景实验已移除固定高度E，并直接接入本Skill区域工具；当前帧重建背景候选，效果几何与候选时钟分离。实验另降低液化相位密度、取消密集随机颜色扰动，对双线性采样逐个检查有权重邻点；非法E/人物支撑/画面外采样回退，不做夹紧/环绕以免产生边缘条带。此处记录实现方向，不把独立实验升级为随包生产renderer。

人物baseline算术与自然gate在无媒体合成输入上回归；五类背景和全背景范围按最新持续测试约定做实片检验，尤其地面/近景是否应该保留、液化大形/颜色与边缘回退观感。不得把数组通过说成当前实片人物缓存或复刻整体已通过。

## 当前人物修复合成接口
`matte_composite.py` 提供 `matte_background_composite(approved_frame, person_frame, changed_background, alpha, *, core_mask, natural_gate=False, natural_frame=None)`。帧为同尺寸uint8三通道、mask为有限0..1；core>0仅允许alpha==1。核心使用approved，其余按独立person_frame与changed_background混合；alpha=0必须等于新背景，0<alpha<1不受approved内容影响。natural_gate优先返回当前完整natural_frame。输入不变，非法核心/软边组合拒绝。

该工具不识别人、不推断头发、不修光流。调用者须从当前帧/合法缓存构造细化alpha和独立人物印刷层，并检查漏分、多分、错误孔洞、拖影与窄边界。软边混旧baseline不是alpha合成，扩大保护mask也不能修复亮壳。旧background_regions工具的非零P排除仅是其严格契约；当前边缘修复可将可靠核心作为P、让软边获得新背景，再使用matte接口。不得把原始confidence非零支撑当成最终核心。

## 背景配方的准确接口
```python
from reference_background_recipes import ReferenceBackgroundRecipes
# xx/yy为当前H×W合法像素网格；仅需NumPy及同包状态工具。
recipes = ReferenceBackgroundRecipes(xx, yy)
changed, allowed = recipes.build(current_bgr, alpha, tick, state,
    policy='full_background')
# 内容限定范围用policy='explicit', allowed_mask=finite_0_to_1_mask。
# 最后用matte_background_composite，whole-frame gate优先。
```
source为uint8 H×W×3 BGR；alpha为同尺寸有限0..1数值，tick仅接受0..1000000整数且不接受bool。policy错误/错形状/NaN/Inf/越界拒绝，不默默降级；自定义palette当前拒绝而非忽略。默认threshold=.48、总过渡宽=.06，点阵按短边缩放，属于实验起点，不是原参考测量。返回allowed不是语义mask，explicit结果在允许权重外保留当前原图；人物排除用于横断采样，最终人物保护必须由matte工具完成。场几何按tick缓存，印刷墨层与采样合法性按当前源帧/alpha重算。

本轮测试复用32缓存mask，人物处理与自然分支未重做。新片回卷色带更宽且配色不再仅紫绿，但边界仍偏数字硬块、褶皱/颗粒不够有机，小人/帽沿边缘仍有视觉风险。观察短闪不能重新设计profile脉宽；42格时间与当前PTS保持审计配置，16自然/104strong不改。单片公园素材不证明缺外部强匹配的两类建筑已经通过。
