#!/usr/bin/env python3
"""
Video Understanding Tools - 视频拉片分析工具

用法：
  python video_understanding_tools.py check
  python video_understanding_tools.py analyze --url <视频URL> --output analysis/
  python video_understanding_tools.py analyze --file <本地视频> --output analysis/
  python video_understanding_tools.py full --video <视频URL或本地路径>
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============== 配置管理 ==============

CONFIG_FILE = Path.home() / ".claude" / "skills" / "video-understanding" / "config.json"
VIDEO_GEN_CONFIG_FILE = Path.home() / ".claude" / "skills" / "video-gen" / "config.json"


def load_config() -> Dict[str, str]:
    """从配置文件加载配置"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass

    if VIDEO_GEN_CONFIG_FILE.exists():
        try:
            with open(VIDEO_GEN_CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass

    return {}


class Config:
    """配置管理类"""

    @classmethod
    def get(cls, key: str, default: str = "") -> str:
        config = load_config()
        return config.get(key, os.getenv(key, default))

    @property
    def MIGOO_API_KEY(self) -> str:
        return self.get("MIGOO_API_KEY", "")

    @property
    def MIGOO_BASE_URL(self) -> str:
        return self.get("MIGOO_BASE_URL", "")

    @property
    def GEMINI_VIDEO_API_URL(self) -> str:
        base_url = self.MIGOO_BASE_URL.rstrip("/")
        return f"{base_url}/v1/publishers/google/models/{self.DEFAULT_MODEL}:generateContent"

    # FileService上传URL（内部服务，从配置读取）
    @property
    def FILE_SERVICE_URL(self) -> str:
        return self.get("FILE_SERVICE_URL", "")

    DEFAULT_MODEL: str = "gemini-2.5-pro"
    FAST_MODEL: str = "gemini-2.5-flash"
    PRO_MODEL: str = "gemini-3.1-pro-preview"


Config = Config()


# ============== 文件上传服务 ==============

async def upload_file(file_path: str) -> Dict[str, Any]:
    """
    上传文件到FileService获取URL

    Args:
        file_path: 本地文件路径

    Returns:
        {"success": bool, "url": str, "error": str}
    """
    import httpx

    if not Config.FILE_SERVICE_URL:
        return {
            "success": False,
            "error": "FILE_SERVICE_URL 未配置，请先上传视频到可访问的URL"
        }

    if not os.path.exists(file_path):
        return {"success": False, "error": f"文件不存在: {file_path}"}

    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)

    logger.info(f"📤 上传文件: {file_name} ({file_size / 1024 / 1024:.2f} MB)")

    try:
        with open(file_path, 'rb') as f:
            file_data = f.read()

        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                Config.FILE_SERVICE_URL,
                files={"file": (file_name, file_data)},
            )

            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"上传失败: {response.status_code} - {response.text[:200]}"
                }

            result = response.json()

            # 从响应中提取URL（根据实际API结构调整）
            file_url = result.get("url") or result.get("file_url") or result.get("data", {}).get("url")

            if not file_url:
                return {
                    "success": False,
                    "error": f"上传成功但未获取到URL: {result}"
                }

            return {
                "success": True,
                "url": file_url,
                "file_name": file_name,
                "file_size": file_size
            }

    except Exception as e:
        logger.error(f"上传失败: {e}")
        return {"success": False, "error": str(e)}


# ============== Gemini 视频理解客户端 ==============

class GeminiVideoClient:
    """Gemini 视频理解客户端"""

    def __init__(self, model: str = None):
        self.api_key = Config.MIGOO_API_KEY
        self.base_url = Config.MIGOO_BASE_URL
        self.model = model or Config.DEFAULT_MODEL

        if not self.api_key:
            raise ValueError("MIGOO_API_KEY 未配置")

    async def analyze_video_url(
        self,
        video_url: str,
        prompt: str,
        mime_type: str = "video/mp4"
    ) -> Dict[str, Any]:
        """分析视频URL"""
        import httpx

        url = Config.GEMINI_VIDEO_API_URL.format(model=self.model)

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"fileData": {"fileUri": video_url, "mimeType": mime_type}},
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {"maxOutputTokens": 8192, "temperature": 0.7}
        }

        logger.info(f"📤 视频分析: {video_url} (model: {self.model})")

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload
                )

                if response.status_code != 200:
                    error_text = response.text
                    return {
                        "success": False,
                        "error": f"API error {response.status_code}: {error_text[:200]}",
                        "video_url": video_url,
                    }

                result = response.json()
                candidates = result.get("candidates", [])
                if candidates:
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    text = ""
                    for part in parts:
                        if "text" in part:
                            text = part["text"]
                            break
                else:
                    text = "无法解析响应"

                usage = result.get("usageMetadata", {})

                return {
                    "success": True,
                    "model": self.model,
                    "video_url": video_url,
                    "analysis": text,
                    "usage_metadata": {
                        "prompt_tokens": usage.get("promptTokenCount", 0),
                        "output_tokens": usage.get("candidatesTokenCount", 0),
                        "total_tokens": usage.get("totalTokenCount", 0),
                    },
                }

        except Exception as e:
            logger.error(f"视频分析失败: {e}")
            return {"success": False, "error": str(e), "video_url": video_url}


# ============== 项目管理 ==============

def create_project_dir(video_name: str) -> str:
    """创建项目目录"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_dir = Path.home() / "video-understanding-projects" / f"{video_name}_{timestamp}"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "analysis").mkdir(exist_ok=True)
    (project_dir / "output").mkdir(exist_ok=True)
    return str(project_dir)


def save_analysis(project_dir: str, filename: str, data: Dict[str, Any]):
    """保存分析结果"""
    analysis_dir = os.path.join(project_dir, "analysis")
    filepath = os.path.join(analysis_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return filepath


def generate_script_markdown(overall_analysis: Dict[str, Any], video_name: str) -> str:
    """生成剧本 Markdown"""
    analysis_text = overall_analysis.get('analysis', '')
    if isinstance(analysis_text, dict):
        analysis_text = analysis_text.get('text', str(analysis_text))

    if analysis_text and ('# 🎬 剧本分析' in analysis_text or '## 第一幕' in analysis_text):
        return analysis_text

    return f"""# 🎬 剧本分析：{video_name}

## 视频概述
- **模型**：{overall_analysis.get('model', '未知')}

## 分析内容

{analysis_text}

---
*本剧本由 video-understanding skill 自动生成*
"""


# ============== 命令行入口 ==============

async def cmd_check(args):
    """检查 API 配置"""
    api_key = Config.MIGOO_API_KEY
    base_url = Config.MIGOO_BASE_URL
    file_service = Config.FILE_SERVICE_URL

    configured = []
    missing = []

    if api_key:
        configured.append("MIGOO_API_KEY")
    else:
        missing.append("MIGOO_API_KEY")

    if base_url:
        configured.append("MIGOO_BASE_URL")
    else:
        missing.append("MIGOO_BASE_URL")

    if file_service:
        configured.append("FILE_SERVICE_URL")
    else:
        missing.append("FILE_SERVICE_URL (可选，用于本地视频上传)")

    print(json.dumps({
        "success": len(missing) == 0 or (api_key and base_url),
        "configured": configured,
        "missing": missing,
        "config_file": str(CONFIG_FILE),
        "models": {"default": Config.DEFAULT_MODEL, "fast": Config.FAST_MODEL, "pro": Config.PRO_MODEL},
    }, indent=2, ensure_ascii=False))

    return 0 if api_key and base_url else 1


async def cmd_analyze(args):
    """视频分析（支持URL和本地文件）"""
    client = GeminiVideoClient(model=args.model)

    prompt = """
请从专业拉片角度分析这个视频，按以下格式输出完整剧本：

# 🎬 剧本分析：{视频名称}

## 视频概述
- 核心主题：XXX
- 年代背景：XXX
- 情感基调：XXX → XXX → XXX

## 人物表
| 人物 | 描述 | 角色 |

---

## 第一幕：XXX（时间范围）
**场景**：XXX
**时间**：XXX
**人物**：XXX

### 【拉片要点】
- 关键镜头语言要点（色调、构图、道具等）

### 【对白/OS】
说话人：「台词」 _（语气）_

### 【动作】
人物动作、表情、穿着

---

## 镜头语言总结
### 运镜特点
### 构图特点
### 光影与色调
"""

    video_url = args.url

    # 本地文件：先上传获取URL
    if args.file and not args.url:
        upload_result = await upload_file(args.file)
        if not upload_result.get("success"):
            print(json.dumps(upload_result, indent=2, ensure_ascii=False))
            return 1
        video_url = upload_result["url"]
        logger.info(f"✅ 文件已上传: {video_url}")

    if not video_url:
        print(json.dumps({"success": False, "error": "请提供 --url 或 --file 参数"}, indent=2))
        return 1

    result = await client.analyze_video_url(video_url, args.prompt or prompt)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if args.output and result.get("success"):
        os.makedirs(args.output, exist_ok=True)
        output_file = os.path.join(args.output, "overall_analysis.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        logger.info(f"分析结果已保存到: {output_file}")

    return 0 if result.get("success") else 1


async def cmd_full(args):
    """完整流程：上传(如需要) + 分析 + 剧本生成"""
    video_path = args.video
    video_name = Path(video_path).stem if not video_path.startswith("http") else "video"
    project_dir = create_project_dir(video_name)
    logger.info(f"项目目录: {project_dir}")

    client = GeminiVideoClient(model=args.model)

    # 获取视频URL
    if video_path.startswith("http"):
        video_url = video_path
    else:
        # 本地文件：上传
        upload_result = await upload_file(video_path)
        if not upload_result.get("success"):
            print(json.dumps(upload_result, indent=2, ensure_ascii=False))
            return 1
        video_url = upload_result["url"]
        logger.info(f"✅ 文件已上传: {video_url}")

    # Gemini分析
    overall_result = await client.analyze_video_url(
        video_url,
        """
请从专业拉片角度全面分析这个视频：

1. **整体主题与叙事**：核心主题、叙事结构、情感基调
2. **视觉风格**：色调与光影、画面构图
3. **音频元素**：台词概述（说话人、语气）、背景音乐
4. **人物与角色**：身份、性格、穿着、关系
5. **场景与空间**：主要场景、切换逻辑
6. **镜头语言**：运镜、构图、角度

请按剧本格式输出。
"""
    )
    save_analysis(project_dir, "overall_analysis.json", overall_result)

    if not overall_result.get("success"):
        print(json.dumps(overall_result, indent=2, ensure_ascii=False))
        return 1

    # 生成剧本
    output_dir = Path(project_dir) / "output"
    script_content = generate_script_markdown(overall_result, video_name)
    script_path = output_dir / "script.md"
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script_content)

    logger.info(f"剧本已保存到: {script_path}")
    print(json.dumps({
        "success": True,
        "project_dir": project_dir,
        "script_path": str(script_path),
        "video_url": video_url,
        "message": "拉片分析完成，请查看 output/script.md",
    }, indent=2, ensure_ascii=False))

    return 0


def main():
    parser = argparse.ArgumentParser(description="Video Understanding Tools")
    subparsers = parser.add_subparsers(dest="command", help="命令")

    # check
    subparsers.add_parser("check", help="检查配置")

    # analyze
    analyze_parser = subparsers.add_parser("analyze", help="视频分析")
    analyze_parser.add_argument("--url", help="视频URL")
    analyze_parser.add_argument("--file", help="本地视频文件")
    analyze_parser.add_argument("--output", default="analysis/", help="输出目录")
    analyze_parser.add_argument("--prompt", help="自定义提示词")
    analyze_parser.add_argument("--model", default=Config.DEFAULT_MODEL, help="模型")

    # full
    full_parser = subparsers.add_parser("full", help="完整流程")
    full_parser.add_argument("--video", required=True, help="视频URL或本地路径")
    full_parser.add_argument("--model", default=Config.DEFAULT_MODEL, help="模型")

    args = parser.parse_args()

    if args.command == "check":
        return asyncio.run(cmd_check(args))
    elif args.command == "analyze":
        return asyncio.run(cmd_analyze(args))
    elif args.command == "full":
        return asyncio.run(cmd_full(args))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())