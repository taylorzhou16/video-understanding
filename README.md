# Video Understanding Skill

AI视频拉片工具，使用Gemini分析视频内容，生成专业剧本。

## 功能

- 视频整体分析：直接分析视频URL，生成完整剧本
- 剧本格式输出：按幕分段，包含拉片要点、对白/OS、动作描述
- 镜头语言分析：运镜特点、构图特点、光影色调

## 安装

```bash
# 安装依赖
pip install -r requirements.txt
```

## 配置

1. 复制配置示例：
```bash
cp config.json.example config.json
```

2. 编辑 `config.json`，填入你的 API Key 和 Base URL：
```json
{
  "MIGOO_API_KEY": "your-api-key-here",
  "MIGOO_BASE_URL": "your-migoo-api-base-url"
}
```

## 使用

### 命令行

```bash
# 检查配置
python video_understanding_tools.py check

# 分析视频URL
python video_understanding_tools.py analyze --url <视频URL> --output analysis/ --video-name "视频名称"

# 生成剧本
python video_understanding_tools.py generate-script --analysis-dir analysis/ --output script.md
```

### 作为Skill使用

在Claude Code中使用 `/video-understanding`：

```
/video-understanding https://example.com/video.mp4
```

## 剧本输出格式

```
# 🎬 剧本分析：视频名称

## 视频概述
- 核心主题
- 年代背景
- 情感基调

## 人物表
| 人物 | 描述 | 角色 |

## 第一幕：XXX（时间范围）
**场景**：XXX
**时间**：XXX
**人物**：XXX

### 【拉片要点】
- 关键镜头语言要点

### 【对白/OS】
说话人：「台词」 _（语气）_

### 【动作】
人物动作描述

---

## 镜头语言总结
### 运镜特点
### 构图特点
### 光影与色调
```

## 与video-gen联动

生成的剧本可直接用于 `/video-gen` 进行视频创作。

## 依赖

- Python 3.9+
- httpx
- google-genai SDK（可选）