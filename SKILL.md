---
name: video-understanding
description: AI视频拉片工具。使用Gemini-3-Pro分析视频内容，进行逐帧拉片、提取镜头语言、生成完整剧本。当用户提供视频文件路径、视频URL链接，或说"拉片"、"分析视频"、"理解视频"、"帮我解析这个视频"时触发。可与/video-gen搭配使用，为其提供剧本素材。
argument-hint: <视频文件路径或URL>
---

# video-understanding 使用指南

**角色**：Video Analyst Agent — 深度理解视频内容、提取专业剧本、为创作提供素材。

**语言要求**：所有回复和剧本产出必须使用中文。

---

## 核心能力

- **视频整体理解**：调用Gemini-3-Pro直接理解视频，分析主题、风格、叙事结构
- **逐帧拉片分析**：按时间间隔抽帧，逐帧分析画面内容、镜头语言、人物动作
- **剧本生成**：产出包含分镜表、台词/旁白、场景氛围、镜头语言的专业剧本
- **与video-gen联动**：生成的剧本可直接用于/video-gen的分镜设计

---

## API 配置

**复用video-gen配置**：此skill复用video-gen的config.json和MIGOO_API_KEY。

**配置文件路径**：`~/.claude/skills/video-gen/config.json`

**API调用方式**（基于Migoo Compass API）：

```python
from google import genai
from google.genai import types

client = genai.Client(
    api_key='<MIGOO_API_KEY>',
    http_options=types.HttpOptions(
        api_version='v1',
        base_url='https://compass.llm.shopee.io/compass-api/v1',
    )
)

# 视频理解示例
response = client.models.generate_content(
    model="gemini-2.5-pro",  # 或 gemini-3.1-pro-preview
    contents=[
        types.Part.from_uri(
            file_uri="https://example.com/demo.mp4",
            mime_type="video/mp4",
        ),
        "请详细分析这个视频的内容...",
    ],
)
```

**支持的模型**：
- `gemini-3.1-pro-preview` - 最新预览版，最强能力
- `gemini-2.5-pro` - 稳定版本，高质量分析
- `gemini-2.5-flash` - 快速版本，成本更低

---

## 工作流程

```
Phase 0: API配置检查 → Phase 1: 视频整体理解 → Phase 2: 逐帧拉片 → Phase 3: 剧本生成 → Phase 4: 文档输出
     5秒              30-60秒               60-120秒            30秒              10秒
```

### 工作流进度清单

```
Task Progress:
- [ ] Phase 0: API配置检查（MIGOO_API_KEY）
- [ ] Phase 1: 视频整体理解（Gemini直接分析视频）
- [ ] Phase 2: 逐帧拉片（按间隔抽帧+逐帧分析）
- [ ] Phase 3: 剧本生成（整合分析结果）
- [ ] Phase 4: 文档输出（生成.md剧本文件）
```

---

## Phase 0: API配置检查

检查MIGOO_API_KEY是否已配置：

```bash
python video_understanding_tools.py check
```

- MIGOO_API_KEY 已配置 → 继续
- 未配置 → 停止并告知用户配置方法

---

## Phase 1: 视频整体理解

### Step 1: 视频输入识别

用户可能提供：
- **本地视频文件路径**：需要先上传到可访问的URL（或使用base64编码）
- **视频URL**：直接使用URL
- **B站/YouTube链接**：调用/bili-transcribe下载后分析

### Step 2: 获取视频元信息

使用ffprobe提取：
- 总时长、分辨率、帧率
- 创建项目目录：`~/video-understanding-projects/{video_name}_{timestamp}/`

### Step 3: Gemini整体理解

调用Gemini直接分析视频（URL方式）：

```python
from video_understanding_tools import GeminiVideoClient

client = GeminiVideoClient()
result = await client.analyze_video(video_url, """
请从以下维度全面分析这个视频：

1. **整体主题与叙事**
   - 核心主题是什么
   - 叙事结构如何（线性/非线性/蒙太奇）
   - 情感基调是什么

2. **视觉风格**
   - 色调与光影特点
   - 画面构图风格
   - 视觉美学风格（写实/动画/实验）

3. **音频元素**
   - 主要台词/旁白内容概述
   - 背景音乐风格与情感配合
   - 音效使用特点

4. **人物与角色**
   - 主要角色身份与性格
   - 人物关系
   - 角色发展与变化

5. **场景与空间**
   - 主要场景有哪些
   - 场景切换逻辑
   - 空间叙事特点
""")
```

**产出**：保存整体分析结果到 `analysis/overall_analysis.json`

---

## Phase 2: 逐帧拉片

### Step 1: 确定抽帧策略

根据视频时长自动选择：
- 短视频（<30s）：每2秒抽一帧
- 中等视频（30s-2min）：每3秒抽一帧
- 长视频（>2min）：每5秒抽一帧

**用户可自定义间隔**：`/video-understanding <视频> --interval 3`

### Step 2: 执行抽帧

使用ffmpeg按间隔抽取关键帧：

```bash
ffmpeg -i video.mp4 -vf "fps=1/{interval}" frames/frame_%03d.jpg
```

### Step 3: 逐帧分析

将关键帧作为图片发送给Gemini进行深度分析：

```python
results = await client.analyze_frames(frame_paths, """
请从专业拉片角度分析这一帧：

1. **画面内容**
   - 场景描述（环境、空间、氛围）
   - 人物状态（表情、动作、位置）
   - 关键道具/物品

2. **镜头语言**
   - 景别（远/全/中/近/特写）
   - 角度（平/仰/俯）
   - 运镜方式（固定/推/拉/摇/移/跟）
   - 构图特点（中心/三分/对称/框架）

3. **时间信息**
   - 预估这一帧在叙事中的位置（开始/发展/高潮/结尾）
   - 与前后帧的关系

4. **情感与氛围**
   - 当前情感状态
   - 氛围特点（紧张/轻松/温馨/冷峻）
""")
```

**产出**：保存逐帧分析结果到 `analysis/frame_analysis.json`

---

## Phase 3: 剧本生成

### Step 1: 整合分析数据

读取 `overall_analysis.json` 和 `frame_analysis.json`

### Step 2: 生成结构化剧本

按照以下模板生成剧本：

```markdown
# {视频标题} 拉片剧本

## 一、视频概述

- **时长**：XX分XX秒
- **风格**：XX风格
- **主题**：XXX
- **叙事结构**：XXX

## 二、人物角色

| 角色 | 身份 | 性格特点 | 关系 |
|------|------|---------|------|
| XX | XX | XX | XX |

## 三、分镜表

### Scene 1: {场景名称}

| 镜号 | 时间码 | 景别 | 镜头运动 | 画面内容 | 台词/旁白 | 情感 | 备注 |
|------|--------|------|---------|---------|---------|------|------|
| 1-01 | 00:00-00:03 | 中景 | 固定 | XXX | XXX | XX | XX |

### Scene 2: {场景名称}
...

## 四、台词/旁白全文

> （按时间顺序整理所有台词和旁白）

## 五、镜头语言分析

### 运镜特点
XXX

### 构图特点
XXX

### 光影与色调
XXX

## 六、场景氛围描述

### Scene 1 氛围
XXX

### Scene 2 氛围
XXX

## 七、与video-gen联动建议

- **适合生成类型**：XXX
- **核心分镜参考**：Scene X, Scene Y
- **角色参考图建议**：XXX
```

---

## Phase 4: 文档输出

### 项目目录结构

```
~/video-understanding-projects/{video_name}_{timestamp}/
├── video.mp4           # 原视频（或下载的视频）
├── frames/             # 抽取的关键帧
│   ├── frame_000.jpg
│   ├── frame_003.jpg
│   └── ...
├── analysis/
│   ├── overall_analysis.json    # 整体分析
│   ├── frame_analysis.json      # 逐帧分析
│   └── video_meta.json          # 视频元信息
├── output/
│   └── script.md                # 最终剧本
└── state.json                   # 项目状态
```

### 输出给用户

1. 展示剧本关键内容摘要
2. 提供剧本文件路径
3. 询问是否需要进一步分析或修改

---

## 与video-gen联动

用户完成拉片后，可直接启动 `/video-gen`：

```
/video-gen ~/video-understanding-projects/{project}/output/script.md
```

**联动方式**：
1. video-gen读取script.md中的分镜表
2. 使用人物角色信息设计参考图
3. 按镜头语言指导分镜设计

---

## 工具调用速查

```bash
# 环境检查
python video_understanding_tools.py check

# 视频整体分析（URL）
python video_understanding_tools.py analyze --url <视频URL> --output analysis/

# 视频整体分析（本地文件，需先上传）
python video_understanding_tools.py analyze --file <视频路径> --output analysis/

# 抽帧
python video_understanding_tools.py extract-frames --video <视频路径> --interval 3 --output frames/

# 逐帧分析
python video_understanding_tools.py analyze-frames --frames-dir frames/ --output analysis/

# 剧本生成
python video_understanding_tools.py generate-script --analysis-dir analysis/ --output output/script.md

# 一键完整流程
python video_understanding_tools.py full --video <视频路径或URL> --interval 3
```

---

## 成本控制建议

根据视频长度和分析深度选择模型：

| 场景 | 推荐模型 | 原因 |
|------|---------|------|
| 短视频快速分析 | gemini-2.5-flash | 成本低，速度快 |
| 专业拉片分析 | gemini-2.5-pro | 高质量，细节准确 |
| 最强分析能力 | gemini-3.1-pro-preview | 最新模型，最强理解 |

**建议**：先用flash快速分析，确认有价值后再用pro深度分析。

---

## 依赖

- FFmpeg 6.0+（视频处理、抽帧）
- Python 3.9+
- google-genai SDK
- MIGOO_API_KEY（Gemini API）
- httpx（HTTP客户端）