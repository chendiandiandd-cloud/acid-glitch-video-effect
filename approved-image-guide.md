# 已确认图片方向：背景参考指南

## 证据层级与计数
用户同意的是图片方向，不是已有renderer整体视觉通过。原建筑截图优先于所有外部补充；截图文件时间不等于源PTS，也不能推导状态序列。共6张外部实图、**5个唯一来源页URL**：E03/E04同页。历史参考板页眉“4个来源页”是计数笔误；随包板只修正该计数标注为5，图片/构图保持不变，不沿用错误。

使用 [参考板](../assets/reference-images/approved-board.png)，配合下列压缩实图。两类缺口仍存在：①黄黑建筑深窗格/亮墙/窄网点；②多色建筑平涂与墨层共存。外部没有强匹配建筑全景，不能将人像补充冒充已校准建筑效果。

## 图片与映射
表中所有本地路径以Skill根目录为基准。状态“接入”仅指公开数组配方有真实调用，不代表视觉验收。

| 编号 / 本地asset | 原作URL | 仅借鉴 | 排除 | 映射状态 / 验证判据 |
| --- | --- | --- | --- | --- |
| E01 `assets/reference-images/e01.jpg` | https://www.youworkforthem.com/extra/E17006/duotone-halftone-effect | 黄黑深墨实块与印刷点阵 | 人像构图、宽过渡、满版网点 | duotone接入：暗/亮稳态各自平面，点只在窄中间调；建筑仍对原01/52验收 |
| E02 `assets/reference-images/e02.jpg` | https://pixelbuddha.net/effects/4315-duotone-halftone-photo-template | 大黑墨压在单紫色平涂的层次关系 | 淡紫配色、人像构图；不是紫/洋红/绿建筑全景 | ink_colorfield接入：换填色不能洗淡暗墨；多色建筑强匹配缺失 |
| E03 `assets/reference-images/e03.jpg` | https://www.blog.123rf.com/trend-report-delving-into-the-liquify-design-trend | 多方向大尺度回卷、分叉、粗细变化 | 灰蓝、光滑金属感、密集细轮廓 | liquid_replace接入：宽色带旋回与分叉，非等距线圈；褶皱自然度待验 |
| E04 `assets/reference-images/e04.jpg` | https://www.blog.123rf.com/trend-report-delving-into-the-liquify-design-trend | 宽色带二维回折与层层折叠 | 青绿单色、金属高光、整套HSV色环 | 与E03同源；检查少数宽带而不是紫绿重复细带，原18优先 |
| E05 `assets/reference-images/e05.jpg` | https://expertphotography.com/create-glitch-art/ | 真实云照片结构上的横向扫描干扰 | 紫粉染色、全屏均匀扫描、将弱撕裂说成强匹配 | horizontal_glitch接入：当前印刷源结构局部横拉，宽/长/间断不等；原34判据优先 |
| E06 `assets/reference-images/e06.jpg` | https://modulate.to/effects/pixel-sort/ | 棕榈场景像素拉伸和局部切断 | 斜向条带、直接复制构图、伪称实现了排序算法 | 横断配方使用局部量化采样/切裂，不是pixel-sort；检查场景墨结构被拉长、不采人物 |

原作实图链接（下载证据，不另算来源页）：
- E03：https://static.wixstatic.com/media/b5a3bf_fdba703f3d5a4f3ea6cd99e025406ec7~mv2.jpg
- E04：https://static.wixstatic.com/media/b5a3bf_3ff5c56630e54944bceccb7745ce04db~mv2.jpg
- E05：https://expertphotography.com/img/2020/03/glitch-watercolor-ultraviolet-clouds-sky.jpg
- E06：https://assets.modulate.to/marketing-assets/effect/pixel-sort/poster-seed-mrd047mt-a9709f24.webp

## 原参考背景锚点
2026-11-05从已核验背景裁图压缩复制，未重新生成、未改色。每张仍可辨识，其余原截图的观察记录见background-structure.md。
- `assets/reference-images/anchor_01.jpg`：深窗格、亮黄墙面与分区颗粒；双色建筑目标。
- `assets/reference-images/anchor_11.jpg`：橙亮面、深墨结构和彩色天空；外部E02只能补墨/填色关系。
- `assets/reference-images/anchor_18.jpg`：背景可整体消失；二维回卷、宽细带与原印刷颗粒，不能要求永远保留建筑。
- `assets/reference-images/anchor_34.jpg`：横向伸长/切断的彩色结构；艺术条带不是E固定高度接缝。

## 实际工具与验证边界
`reference_background_recipes.py`提供BGR数组配方，使用同包background_state构建双色、墨填色与显式替换。少数不等宽色带经多中心二维旋回、分支距离场组织；横断从当前印刷场景局部量化采样拉伸/切裂，检查每个源/目标的允许区及alpha==0，无夹紧采样、环绕或人物污染。内部clip只用于合法索引读取，越界结果永不写入。source返回当前源图。full_background是明确艺术范围，不是语义识别。

使用同包matte接口合成：可靠核心alpha=1保持原内部，软边混独立人物层和新背景；whole-frame natural_gate最后选择当前PTS完整自然分支。禁止把背景状态填进原42格时间profile。跨比例/暗光/切镜须重建区域、校准阈值，不能将公园单次测试推广为建筑、人像、宠物等全部通过。

本轮公开逻辑已经接入实验renderer，仍非完整生产入口。回卷的自然褶皱、背景颗粒与原建筑墨层组织、人物帽沿/肩部和背景小人边缘继续待视觉验收；不能因通过有限调色、点阵或格式测试就宣布整体复刻。
