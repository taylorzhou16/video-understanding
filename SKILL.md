---
name: video-understanding
description: AI视频拉片工具。使用Gemini分析视频内容，提取镜头语言，生成完整剧本。当用户提供视频文件路径、视频URL链接，或说"拉片"、"分析视频"、"理解视频"、"帮我解析这个视频"时触发。可与/video-gen搭配使用，为其提供剧本素材。
argument-hint: <视频URL或本地路径>
---

# video-understanding 使用指南

**角色**：Video Analyst Agent — 深度理解视频内容、提取专业剧本、为创作提供素材。

**语言要求**：所有回复和剧本产出必须使用中文。

---

## 核心能力

- **视频整体理解**：调用Gemini直接理解视频，分析主题、风格、叙事结构
- **本地视频支持**：自动上传本地视频获取URL，再调用Gemini分析
- **剧本生成**：产出包含分镜表、台词/旁白、场景氛围、镜头语言的专业剧本
- **与video-gen联动**：生成的剧本可直接用于/video-gen的分镜设计

---

## API 配置

**配置文件路径**：`~/.claude/skills/video-understanding/config.json`

**需要配置**：
- `MIGOO_API_KEY` - API密钥
- `MIGOO_BASE_URL` - Migoo Gemini API服务器地址
- `FILE_SERVICE_URL` - 文件上传服务URL（可选，用于本地视频）

**支持的模型**：
- `gemini-3.1-pro-preview` - 最新预览版，最强能力
- `gemini-2.5-pro` - 稳定版本，高质量分析（默认）
- `gemini-2.5-flash` - 快速版本，成本更低

---

## 工作流程

**视频URL分析**：
```
Phase 0: 配置检查 → Phase 1: Gemini分析 → Phase 2: 剧本生成 → Phase 3: 输出
     5秒            30-60秒            10秒            5秒
```

**本地视频分析**：
```
Phase 0: 配置检查 → Phase 1: 上传获取URL → Phase 2: Gemini分析 → Phase 3: 剧本生成
     5秒            10-30秒             30-60秒            10秒
```

---

## Phase 0: API配置检查

```bash
python video_understanding_tools.py check
```

---

## Phase 1: 视频输入

### 方式1：视频URL

用户直接提供可访问的视频URL，Gemini直接分析。

### 方式2：本地视频文件

用户提供本地视频路径，先上传到FileService获取URL，再调用Gemini分析。

```python
# 上传本地文件
upload_result = await upload_file(local_video_path)
video_url = upload_result["url"]

# Gemini分析
client = GeminiVideoClient()
result = await client.analyze_video_url(video_url, prompt)
```

---

## Phase 2: Gemini分析

调用Gemini直接分析视频内容，按剧本格式输出：

```markdown
# 🎬 剧本分析：视频名称

## 视频概述
- 核心主题、年代背景、情感基调

## 人物表
| 人物 | 描述 | 角色 |

## 第一幕：XXX
**场景**：XXX
**时间**：XXX

### 【拉片要点】
### 【对白/OS】
### 【动作】

---

## 镜头语言总结
```

---

## Phase 3: 文档输出

**项目目录结构**：

```
~/video-understanding-projects/{video_name}_{timestamp}/
├── analysis/
│   └── overall_analysis.json
└── output/
    └── script.md
```

---

## 与video-gen联动

```
/video-gen ~/video-understanding-projects/{project}/output/script.md
```

---

## 工具调用速查

```bash
# 环境检查
python video_understanding_tools.py check

# 分析视频URL
python video_understanding_tools.py analyze --url <视频URL> --output analysis/

# 分析本地视频
python video_understanding_tools.py analyze --file <本地视频路径> --output analysis/

# 一键完整流程
python video_understanding_tools.py full --video <视频URL或本地路径>
```

---

## 依赖

- Python 3.9+
- httpx（HTTP客户端）
- MIGOO_API_KEY + MIGOO_BASE_URL（必需）
- FILE_SERVICE_URL（可选，用于本地视频上传）