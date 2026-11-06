# 已有轻量人物权重

随包携带 `yolov8n-seg.onnx`（13,681,633字节，约13.05MiB），复制日期2026-11-06。
源：工作区 `models/yolov8n-seg.onnx`，既有获取记录为2026-11-04，公开模型项目 https://huggingface.co/Kalray/yolov8n-seg 。没有本次联网下载，没有私有视频或缓存打包。

SHA-256：`aaa517ec9fd9a2e4e931109b372a14d952ca02cebb67d086a2666fd360502793`

仅显式开发核对权重来源时校验（正常渲染已计算一次模型缓存指纹，不重复执行）：`python3 -c "import hashlib; from pathlib import Path; print(hashlib.sha256(Path('models/yolov8n-seg.onnx').read_bytes()).hexdigest())"`（Skill根目录）。

默认模型路径由入口自身位置解析，不依赖cwd。可用 `--model /absolute/path/yolov8n-seg.onnx` 自带同一Kalray raw-head导出；通用Ultralytics合并输出导出并非兼容替代品。自行提供权重须核对来源、SHA-256与输出头格式；入口不会自动下载，也不会自动换模型。

缺权重时 `auto` / `cache-only` 明确报错；明确无人物处理使用 `--segmentation none`，不加载权重、不导入ONNXRuntime、不做分割推理，但不是已准确判断无人。`auto`的detail模式是原有整帧加左右重叠裁块、全部person实例并集（每锚点3次forward），没有新增语义模型。
