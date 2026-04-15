#!/usr/bin/env python3
"""
Video Understanding Tools - 视频拉片分析工具

用法：
  python video_understanding_tools.py check
  python video_understanding_tools.py analyze --url <视频URL> --output analysis/
  python video_understanding_tools.py analyze --file <视频路径> --output analysis/
  python video_understanding_tools.py extract-frames --video <视频路径> --interval 3 --output frames/
  python video_understanding_tools.py analyze-frames --frames-dir frames/ --output analysis/
  python video_understanding_tools.py generate-script --analysis-dir analysis/ --output output/script.md
  python video_understanding_tools.py full --video <视频路径或URL> --interval 3
"""

import argparse
import asyncio
import base64
import json
import logging
import os
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============== 配置管理 ==============

# 配置文件路径（优先使用本skill的配置，不存在则复用video-gen的）
CONFIG_FILE = Path.home() / ".claude" / "skills" / "video-understanding" / "config.json"
VIDEO_GEN_CONFIG_FILE = Path.home() / ".claude" / "skills" / "video-gen" / "config.json"


def load_config() -> Dict[str, str]:
    """从配置文件加载配置"""
    # 优先使用本skill的配置文件
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass

    # 备用：复用video-gen的配置文件
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
        """从配置文件或环境变量获取配置"""
        config = load_config()
        return config.get(key, os.getenv(key, default))

    @property
    def MIGOO_API_KEY(self) -> str:
        return self.get("MIGOO_API_KEY", "")

    # API Base URL（从配置文件读取，必须配置）
    @property
    def MIGOO_BASE_URL(self) -> str:
        return self.get("MIGOO_BASE_URL", "")

    @property
    def GEMINI_VIDEO_API_URL(self) -> str:
        base_url = self.MIGOO_BASE_URL.rstrip("/")
        return f"{base_url}/v1/publishers/google/models/{self.DEFAULT_MODEL}:generateContent"

    # 默认模型
    DEFAULT_MODEL: str = "gemini-2.5-pro"
    FAST_MODEL: str = "gemini-2.5-flash"
    PRO_MODEL: str = "gemini-3.1-pro-preview"


Config = Config()


# ============== Gemini 视频理解客户端 ==============

class GeminiVideoClient:
    """
    Gemini 视频理解客户端

    使用 Migoo Compass API 调用 Gemini 模型进行视频分析
    """

    def __init__(self, model: str = None):
        """
        初始化客户端

        Args:
            model: Gemini 模型名称，默认使用 gemini-2.5-pro
        """
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
        """
        分析视频URL（使用httpx直接调用API）

        Args:
            video_url: 视频URL地址
            prompt: 分析提示词
            mime_type: 视频MIME类型

        Returns:
            分析结果字典
        """
        import httpx

        # 使用正确的API URL格式
        url = Config.GEMINI_VIDEO_API_URL.format(model=self.model)

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "fileData": {
                                "fileUri": video_url,
                                "mimeType": mime_type
                            }
                        },
                        {
                            "text": prompt
                        }
                    ]
                }
            ],
            "generationConfig": {
                "maxOutputTokens": 8192,
                "temperature": 0.7
            }
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

                # 提取响应文本
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

                # 提取usage metadata
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
            return {
                "success": False,
                "error": str(e),
                "video_url": video_url,
            }

    async def _analyze_video_url_httpx(
        self,
        video_url: str,
        prompt: str,
        mime_type: str = "video/mp4"
    ) -> Dict[str, Any]:
        """
        使用 httpx 直接调用 API（SDK未安装时的fallback）
        """
        import httpx

        # 使用完整的API URL格式
        url = Config.GEMINI_VIDEO_API_URL.format(model=self.model)

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "fileData": {
                                "fileUri": video_url,
                                "mimeType": mime_type
                            }
                        },
                        {
                            "text": prompt
                        }
                    ]
                }
            ],
            "generationConfig": {
                "maxOutputTokens": 8192,
                "temperature": 0.7
            }
        }

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

                # 提取响应文本
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

                return {
                    "success": True,
                    "model": self.model,
                    "video_url": video_url,
                    "analysis": text,
                    "usage_metadata": result.get("usageMetadata", None),
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "video_url": video_url,
            }

    async def analyze_image_url(
        self,
        image_url: str,
        prompt: str,
        mime_type: str = "image/jpeg"
    ) -> Dict[str, Any]:
        """
        分析图片URL（用于逐帧分析）
        """
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(
                    api_version='v1',
                    base_url=self.base_url,
                )
            )

            response = client.models.generate_content(
                model=self.model,
                contents=[
                    types.Part.from_uri(
                        file_uri=image_url,
                        mime_type=mime_type,
                    ),
                    prompt,
                ],
            )

            return {
                "success": True,
                "model": self.model,
                "image_url": image_url,
                "analysis": response.text,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "image_url": image_url,
            }

    async def analyze_image_file(
        self,
        image_path: str,
        prompt: str
    ) -> Dict[str, Any]:
        """
        分析本地图片文件（使用base64编码，异步调用）
        """
        import asyncio

        if not os.path.exists(image_path):
            return {
                "success": False,
                "error": f"图片不存在: {image_path}",
            }

        # 读取图片并编码
        with open(image_path, 'rb') as f:
            image_data = f.read()

        ext = os.path.splitext(image_path)[1].lower()
        mime_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
        }
        mime_type = mime_map.get(ext, 'image/jpeg')

        base64_image = base64.b64encode(image_data).decode('utf-8')

        # 直接使用 httpx 异步调用（比 SDK 更快且真正异步）
        return await self._analyze_image_base64_httpx(base64_image, mime_type, prompt, image_path)

    async def _analyze_image_base64_httpx(
        self,
        base64_image: str,
        mime_type: str,
        prompt: str,
        image_path: str
    ) -> Dict[str, Any]:
        """使用 httpx 直接调用图片分析 API"""
        import httpx

        # 使用完整的API URL（包含 /v1）
        url = Config.GEMINI_VIDEO_API_URL.format(model=self.model)

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "inlineData": {
                                "data": base64_image,
                                "mimeType": mime_type
                            }
                        },
                        {
                            "text": prompt
                        }
                    ]
                }
            ],
            "generationConfig": {
                "maxOutputTokens": 2048,
                "temperature": 0.7
            }
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload
                )

                if response.status_code != 200:
                    return {
                        "success": False,
                        "error": f"API error {response.status_code}",
                        "image_path": image_path,
                    }

                result = response.json()
                candidates = result.get("candidates", [])
                text = ""
                if candidates:
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    for part in parts:
                        if "text" in part:
                            text = part["text"]
                            break

                return {
                    "success": True,
                    "model": self.model,
                    "image_path": image_path,
                    "analysis": text,
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "image_path": image_path,
            }

    async def analyze_batch_images(
        self,
        image_paths: List[str],
        prompt: str,
        concurrency: int = 5
    ) -> List[Dict[str, Any]]:
        """
        批量分析多张图片（并发处理）

        Args:
            image_paths: 图片路径列表
            prompt: 分析提示词
            concurrency: 并发数量，默认5（避免API限流）
        """
        import asyncio

        # 使用信号量控制并发数
        semaphore = asyncio.Semaphore(concurrency)

        async def analyze_with_semaphore(path: str) -> Dict[str, Any]:
            async with semaphore:
                return await self.analyze_image_file(path, prompt)

        # 并发执行所有任务
        results = await asyncio.gather(
            *[analyze_with_semaphore(path) for path in image_paths],
            return_exceptions=True
        )

        # 处理异常结果
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append({
                    "success": False,
                    "error": str(result),
                    "image_path": image_paths[i],
                })
            else:
                final_results.append(result)

        return final_results


# ============== 视频元信息提取 ==============

def get_video_metadata(video_path: str) -> Dict[str, Any]:
    """
    使用 ffprobe 提取视频元信息

    Returns:
        {
            "duration": float,  # 时长（秒）
            "width": int,
            "height": int,
            "fps": float,
            "format": str,
            "size": int,  # 文件大小（字节）
        }
    """
    if not os.path.exists(video_path):
        return {"success": False, "error": f"视频不存在: {video_path}"}

    try:
        # 获取基本信息
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            video_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return {"success": False, "error": "ffprobe 执行失败"}

        data = json.loads(result.stdout)

        # 提取视频流信息
        video_stream = None
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break

        if not video_stream:
            return {"success": False, "error": "未找到视频流"}

        format_info = data.get("format", {})

        # 计算 fps
        fps_str = video_stream.get("r_frame_rate", "30/1")
        if "/" in fps_str:
            num, den = fps_str.split("/")
            fps = float(num) / float(den)
        else:
            fps = float(fps_str)

        return {
            "success": True,
            "video_path": video_path,
            "duration": float(format_info.get("duration", 0)),
            "width": int(video_stream.get("width", 0)),
            "height": int(video_stream.get("height", 0)),
            "fps": fps,
            "format": format_info.get("format_name", ""),
            "size": int(format_info.get("size", 0)),
            "bit_rate": int(format_info.get("bit_rate", 0)),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============== 视频抽帧 ==============

def extract_frames(
    video_path: str,
    interval: int,
    output_dir: str,
    max_frames: int = 10
) -> Dict[str, Any]:
    """
    按时间间隔抽取视频帧（最多 max_frames 帧）

    Args:
        video_path: 视频文件路径
        interval: 抽帧间隔（秒）
        output_dir: 输出目录
        max_frames: 最大抽帧数量，默认10帧

    Returns:
        {
            "success": bool,
            "frames": List[str],  # 生成的帧文件路径
            "count": int,
            "interval": int,
        }
    """
    if not os.path.exists(video_path):
        return {"success": False, "error": f"视频不存在: {video_path}"}

    os.makedirs(output_dir, exist_ok=True)

    try:
        # 使用 ffmpeg 抽帧，限制最多 max_frames 帧
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-vf", f"fps=1/{interval}",
            "-q:v", "2",  # 高质量
            "-frames:v", str(max_frames),  # 限制最多输出 max_frames 帧
            "-y",  # 覆盖已存在文件
            os.path.join(output_dir, "frame_%03d.jpg")
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            return {"success": False, "error": f"ffmpeg 执行失败: {result.stderr[:200]}"}

        # 列出生成的帧文件
        frame_files = sorted([
            f for f in os.listdir(output_dir)
            if f.startswith("frame_") and f.endswith(".jpg")
        ])

        frame_paths = [os.path.join(output_dir, f) for f in frame_files]

        return {
            "success": True,
            "video_path": video_path,
            "interval": interval,
            "output_dir": output_dir,
            "frames": frame_paths,
            "count": len(frame_paths),
            "max_frames": max_frames,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============== 项目管理 ==============

def create_project_dir(video_name: str) -> str:
    """
    创建项目目录

    Args:
        video_name: 视频名称（不含扩展名）

    Returns:
        项目目录路径
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_dir = Path.home() / "video-understanding-projects" / f"{video_name}_{timestamp}"
    project_dir.mkdir(parents=True, exist_ok=True)

    # 创建子目录
    (project_dir / "frames").mkdir(exist_ok=True)
    (project_dir / "analysis").mkdir(exist_ok=True)
    (project_dir / "output").mkdir(exist_ok=True)

    return str(project_dir)


def save_state(project_dir: str, state: Dict[str, Any]):
    """保存项目状态"""
    state_path = os.path.join(project_dir, "state.json")
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def save_analysis(project_dir: str, filename: str, data: Dict[str, Any]):
    """保存分析结果"""
    analysis_dir = os.path.join(project_dir, "analysis")
    filepath = os.path.join(analysis_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return filepath


# ============== 剧本生成 ==============

def generate_script_markdown(
    overall_analysis: Dict[str, Any],
    frame_analysis: List[Dict[str, Any]],
    video_meta: Dict[str, Any],
    video_name: str
) -> str:
    """
    生成剧本 Markdown 文件
    直接使用Gemini的分析结果作为剧本内容
    """
    # 从整体分析中提取文本（这就是Gemini输出的剧本内容）
    analysis_text = overall_analysis.get('analysis', '')
    if isinstance(analysis_text, dict):
        analysis_text = analysis_text.get('text', str(analysis_text))

    # 如果Gemini已经按剧本格式输出，直接返回
    if analysis_text and '# 🎬 剧本分析' in analysis_text or '## 第一幕' in analysis_text:
        # 直接使用Gemini输出的内容作为剧本
        return analysis_text

    # 如果Gemini没有输出剧本格式，生成简单版本
    duration = video_meta.get("duration", 0)
    minutes = int(duration // 60)
    seconds = int(duration % 60)

    return f"""# 🎬 剧本分析：{video_name}

## 视频概述
- **时长**：{minutes}分{seconds}秒
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
    if api_key:
        print(json.dumps({
            "success": True,
            "message": "MIGOO_API_KEY 已配置",
            "config_file": str(CONFIG_FILE),
            "default_model": Config.DEFAULT_MODEL,
            "fast_model": Config.FAST_MODEL,
            "pro_model": Config.PRO_MODEL,
        }, indent=2, ensure_ascii=False))
        return 0
    else:
        print(json.dumps({
            "success": False,
            "error": "MIGOO_API_KEY 未配置",
            "hint": f"请在 {CONFIG_FILE} 中添加 MIGOO_API_KEY",
            "config_file": str(CONFIG_FILE),
        }, indent=2, ensure_ascii=False))
        return 1


async def cmd_analyze(args):
    """视频整体分析"""
    client = GeminiVideoClient(model=args.model)

    # 专门设计用于生成剧本格式的prompt
    prompt = """
请从专业拉片角度分析这个视频，按以下格式输出完整剧本：

# 🎬 剧本分析：{视频名称}

## 视频概述
- 核心主题：XXX
- 年代背景：XXX
- 情感基调：XXX → XXX → XXX

## 人物表
| 人物 | 描述 | 角色 |
列出所有出场人物

---

## 第一幕：XXX（时间范围）
**场景**：XXX
**时间**：XXX
**人物**：XXX

### 【拉片要点】
- 列出3-5个关键镜头语言要点（色调、构图、道具等）

### 【对白/OS】
说话人：「台词内容」 _（语气/情感）_

### 【动作】
详细描述人物的动作、表情、穿着

---

## 第二幕：XXX
...（按实际视频内容分段）

---

## 镜头语言总结
### 运镜特点
### 构图特点
### 光影与色调

请严格按照以上格式输出，每个幕都要包含：场景、时间、人物、拉片要点、对白/OS、动作。
"""

    if args.url:
        result = await client.analyze_video_url(args.url, args.prompt or prompt)
    elif args.file:
        # 本地文件需要先处理
        video_meta = get_video_metadata(args.file)
        print(json.dumps(video_meta, indent=2, ensure_ascii=False))

        # 本地文件暂不支持直接分析，需要上传到URL
        result = {
            "success": False,
            "error": "本地视频文件分析暂不支持，请提供视频URL",
            "hint": "可以先使用 /bili-transcribe 下载B站视频获取URL，或上传视频到可访问的URL",
        }
    else:
        result = {"success": False, "error": "请提供 --url 或 --file 参数"}

    print(json.dumps(result, indent=2, ensure_ascii=False))

    if args.output:
        os.makedirs(args.output, exist_ok=True)
        output_file = os.path.join(args.output, "overall_analysis.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        logger.info(f"分析结果已保存到: {output_file}")

    return 0 if result.get("success") else 1


async def cmd_extract_frames(args):
    """视频抽帧"""
    result = extract_frames(args.video, args.interval, args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("success") else 1


async def cmd_analyze_frames(args):
    """逐帧分析"""
    client = GeminiVideoClient(model=args.model)

    # 获取所有帧文件
    frames_dir = Path(args.frames_dir)
    frame_files = sorted([
        str(f) for f in frames_dir.glob("frame_*.jpg")
    ])

    if not frame_files:
        print(json.dumps({
            "success": False,
            "error": f"目录中没有找到帧文件: {args.frames_dir}",
        }, indent=2, ensure_ascii=False))
        return 1

    logger.info(f"找到 {len(frame_files)} 个帧文件，开始分析...")

    prompt = args.prompt or """
请从专业拉片角度分析这一帧：

1. **画面内容**：场景描述、人物状态、关键道具
2. **镜头语言**：景别（远/全/中/近/特写）、角度（平/仰/俯）、运镜、构图
3. **时间信息**：叙事位置、与前后帧关系
4. **情感与氛围**：当前情感、氛围特点

请以简洁结构化方式输出。
"""

    results = await client.analyze_batch_images(frame_files, prompt)

    # 保存结果
    if args.output:
        os.makedirs(args.output, exist_ok=True)
        output_file = os.path.join(args.output, "frame_analysis.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info(f"逐帧分析结果已保存到: {output_file}")

    print(json.dumps({
        "success": True,
        "frames_count": len(results),
        "output": args.output,
        "results": results[:3] if len(results) > 3 else results,  # 只显示前3个结果
    }, indent=2, ensure_ascii=False))

    return 0


async def cmd_generate_script(args):
    """生成剧本"""
    analysis_dir = Path(args.analysis_dir)

    # 读取分析结果
    overall_file = analysis_dir / "overall_analysis.json"
    frame_file = analysis_dir / "frame_analysis.json"
    meta_file = analysis_dir / "video_meta.json"

    overall_analysis = {}
    frame_analysis = []
    video_meta = {}

    if overall_file.exists():
        with open(overall_file, "r", encoding="utf-8") as f:
            overall_analysis = json.load(f)

    if frame_file.exists():
        with open(frame_file, "r", encoding="utf-8") as f:
            frame_analysis = json.load(f)

    if meta_file.exists():
        with open(meta_file, "r", encoding="utf-8") as f:
            video_meta = json.load(f)

    video_name = args.video_name or "未命名视频"

    script_content = generate_script_markdown(
        overall_analysis,
        frame_analysis,
        video_meta,
        video_name
    )

    # 保存剧本
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(script_content)

    logger.info(f"剧本已保存到: {args.output}")
    print(json.dumps({
        "success": True,
        "output": args.output,
        "script_preview": script_content[:500] + "...\n",
    }, indent=2, ensure_ascii=False))

    return 0


async def cmd_full(args):
    """完整流程：视频整体分析 + 剧本生成（无逐帧分析）"""
    # 1. 创建项目目录
    video_name = Path(args.video).stem if not args.video.startswith("http") else "video"
    project_dir = create_project_dir(video_name)
    logger.info(f"项目目录: {project_dir}")

    # 2. 视频整体分析
    client = GeminiVideoClient(model=args.model)

    if args.video.startswith("http"):
        # 直接分析URL
        video_url = args.video
        overall_result = await client.analyze_video_url(
            video_url,
            """
请从专业拉片角度全面分析这个视频：

1. **整体主题与叙事**：核心主题、叙事结构（按幕分段）、情感基调
2. **视觉风格**：色调与光影、画面构图、美学风格
3. **音频元素**：台词概述（包含说话人、语气）、背景音乐风格、音效特点
4. **人物与角色**：主要角色身份、性格、穿着、关系
5. **场景与空间**：主要场景、场景切换逻辑、空间叙事特点
6. **镜头语言**：运镜特点、构图特点、角度使用

请以结构化方式输出，便于生成专业剧本。
"""
        )
        save_analysis(project_dir, "overall_analysis.json", overall_result)
    else:
        # 本地文件需要先上传获取URL
        print("本地文件分析需要先上传获取URL...")
        print("请使用已上传的视频URL，或手动上传后提供URL")
        return 1

    # 3. 生成剧本
    analysis_dir = Path(project_dir) / "analysis"
    output_dir = Path(project_dir) / "output"
    output_dir.mkdir(exist_ok=True)

    overall_file = analysis_dir / "overall_analysis.json"
    if overall_file.exists():
        with open(overall_file, "r", encoding="utf-8") as f:
            overall_analysis = json.load(f)

    script_content = generate_script_markdown(
        overall_analysis,
        [],  # 不再需要逐帧分析数据
        {},  # video_meta
        video_name
    )

    script_path = output_dir / "script.md"
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script_content)

    logger.info(f"剧本已保存到: {script_path}")
    print(json.dumps({
        "success": True,
        "project_dir": project_dir,
        "script_path": str(script_path),
        "message": "拉片分析完成，请查看 output/script.md",
    }, indent=2, ensure_ascii=False))

    return 0


def main():
    parser = argparse.ArgumentParser(description="Video Understanding Tools")
    subparsers = parser.add_subparsers(dest="command", help="命令")

    # check 命令
    check_parser = subparsers.add_parser("check", help="检查 API 配置")

    # analyze 命令
    analyze_parser = subparsers.add_parser("analyze", help="视频整体分析")
    analyze_parser.add_argument("--url", help="视频URL")
    analyze_parser.add_argument("--file", help="本地视频文件路径")
    analyze_parser.add_argument("--output", default="analysis/", help="输出目录")
    analyze_parser.add_argument("--prompt", help="自定义分析提示词")
    analyze_parser.add_argument("--model", default=Config.DEFAULT_MODEL, help="模型名称")
    analyze_parser.add_argument("--video-name", default="未命名视频", help="视频名称")

    # extract-frames 命令
    extract_parser = subparsers.add_parser("extract-frames", help="视频抽帧")
    extract_parser.add_argument("--video", required=True, help="视频文件路径")
    extract_parser.add_argument("--interval", type=int, default=3, help="抽帧间隔（秒）")
    extract_parser.add_argument("--output", default="frames/", help="输出目录")

    # analyze-frames 命令
    frames_parser = subparsers.add_parser("analyze-frames", help="逐帧分析")
    frames_parser.add_argument("--frames-dir", required=True, help="帧文件目录")
    frames_parser.add_argument("--output", default="analysis/", help="输出目录")
    frames_parser.add_argument("--prompt", help="自定义分析提示词")
    frames_parser.add_argument("--model", default=Config.DEFAULT_MODEL, help="模型名称")

    # generate-script 命令
    script_parser = subparsers.add_parser("generate-script", help="生成剧本")
    script_parser.add_argument("--analysis-dir", required=True, help="分析结果目录")
    script_parser.add_argument("--output", default="output/script.md", help="剧本输出路径")
    script_parser.add_argument("--video-name", help="视频名称")

    # full 命令
    full_parser = subparsers.add_parser("full", help="完整流程")
    full_parser.add_argument("--video", required=True, help="视频路径或URL")
    full_parser.add_argument("--interval", type=int, default=3, help="抽帧间隔")
    full_parser.add_argument("--model", default=Config.DEFAULT_MODEL, help="模型名称")

    args = parser.parse_args()

    if args.command == "check":
        return asyncio.run(cmd_check(args))
    elif args.command == "analyze":
        return asyncio.run(cmd_analyze(args))
    elif args.command == "extract-frames":
        return asyncio.run(cmd_extract_frames(args))
    elif args.command == "analyze-frames":
        return asyncio.run(cmd_analyze_frames(args))
    elif args.command == "generate-script":
        return asyncio.run(cmd_generate_script(args))
    elif args.command == "full":
        return asyncio.run(cmd_full(args))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())