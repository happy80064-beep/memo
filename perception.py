"""
Perception Module - 多模态感知层 (The Senses)
处理附件：图片、音频、文档等，转换为文本描述
"""

import base64
import mimetypes
from typing import Optional
from urllib.parse import urlparse

import requests
from langchain_core.messages import HumanMessage

from llm_factory import get_vision_llm


def _is_url(path: str) -> bool:
    """判断是否为 URL"""
    parsed = urlparse(path)
    return parsed.scheme in ("http", "https")


def _fetch_image_base64(file_url: str) -> tuple[str, str]:
    """获取图片并转为 base64

    Returns:
        (base64_data, mime_type)
    """
    if _is_url(file_url):
        # 从 URL 获取
        response = requests.get(file_url, timeout=30)
        response.raise_for_status()
        content = response.content
        # 从响应头或 URL 推断 MIME 类型
        content_type = response.headers.get("Content-Type", "")
        if not content_type or content_type == "application/octet-stream":
            content_type, _ = mimetypes.guess_type(file_url)
        mime_type = content_type or "image/jpeg"
    else:
        # 本地文件
        with open(file_url, "rb") as f:
            content = f.read()
        mime_type, _ = mimetypes.guess_type(file_url)
        mime_type = mime_type or "image/jpeg"

    base64_data = base64.b64encode(content).decode("utf-8")
    return base64_data, mime_type


def _build_vision_message(
    image_base64: str, mime_type: str, prompt: Optional[str] = None
) -> HumanMessage:
    """构建 Vision 模型的消息"""
    default_prompt = (
        "请详细描述这张图片的内容。包括：\n"
        "1. 图片整体场景和主题\n"
        "2. 包含的主要元素、物体、人物\n"
        "3. 文字内容（如果有，请完整提取）\n"
        "4. 图片传达的信息或用途\n"
        "请用中文回答。"
    )

    return HumanMessage(
        content=[
            {"type": "text", "text": prompt or default_prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{image_base64}",
                    "detail": "auto",
                },
            },
        ]
    )


def process_image(file_url: str, prompt: Optional[str] = None) -> str:
    """处理图片，返回文本描述

    Args:
        file_url: 图片 URL 或本地路径
        prompt: 自定义提示词，默认使用详细描述模板

    Returns:
        图片内容的文本描述
    """
    # 1. 获取图片 base64
    image_base64, mime_type = _fetch_image_base64(file_url)

    # 2. 构建消息
    message = _build_vision_message(image_base64, mime_type, prompt)

    # 3. 调用 Vision 模型
    llm = get_vision_llm()
    response = llm.invoke([message])

    return response.content


def process_audio(file_url: str) -> str:
    """处理音频文件 (转录为文本)

    Args:
        file_url: 音频 URL 或本地路径

    Returns:
        音频转录文本

    Note:
        当前使用 placeholder 实现，建议接入:
        - Whisper API (OpenAI)
        - 阿里云语音识别
        - 讯飞语音听写
    """
    # TODO: 接入实际音频转录服务
    # 示例占位实现 - 可替换为 Whisper 等
    llm = get_vision_llm()

    prompt = f"""
用户上传了一个音频文件: {file_url}

请返回以下格式的占位响应，表示需要接入音频转录服务:
[音频待转录] 文件地址: {file_url}

建议接入: Whisper API / 阿里云语音识别 / 讯飞语音听写
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content


def process_document(file_url: str, mime_type: str) -> str:
    """处理文档 (PDF, DOCX, etc.)

    Args:
        file_url: 文档 URL 或本地路径
        mime_type: 文档 MIME 类型

    Returns:
        文档内容文本

    Note:
        当前需要结合外部文档解析服务:
        - PyPDF2 / pdfplumber (PDF)
        - python-docx (DOCX)
        - unstructured (通用文档)
    """
    # 尝试获取文档内容
    try:
        if _is_url(file_url):
            response = requests.get(file_url, timeout=30)
            response.raise_for_status()
            content_bytes = response.content
        else:
            with open(file_url, "rb") as f:
                content_bytes = f.read()
    except Exception as e:
        return f"[文档读取失败] {str(e)}"

    # 根据 MIME 类型处理
    if mime_type == "application/pdf":
        return _process_pdf(content_bytes, file_url)
    elif mime_type in (
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ):
        return _process_docx(content_bytes, file_url)
    elif mime_type.startswith("text/"):
        # 纯文本直接返回
        try:
            return content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return content_bytes.decode("gbk", errors="ignore")
    else:
        return f"[不支持的文档类型] {mime_type}，文件地址: {file_url}"


def _process_pdf(content_bytes: bytes, source: str) -> str:
    """处理 PDF 文档"""
    try:
        # 尝试使用 PyPDF2
        from PyPDF2 import PdfReader
        import io

        reader = PdfReader(io.BytesIO(content_bytes))
        text_parts = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                text_parts.append(f"--- 第 {i+1} 页 ---\n{text}")

        return "\n\n".join(text_parts) if text_parts else f"[PDF 无文本内容] {source}"
    except ImportError:
        return f"[PDF 处理需要 PyPDF2] pip install PyPDF2, 文件地址: {source}"
    except Exception as e:
        return f"[PDF 解析失败] {str(e)}, 文件地址: {source}"


def _process_docx(content_bytes: bytes, source: str) -> str:
    """处理 DOCX 文档"""
    try:
        from docx import Document
        import io

        doc = Document(io.BytesIO(content_bytes))
        text_parts = []
        for para in doc.paragraphs:
            if para.text.strip():
                text_parts.append(para.text)

        return "\n".join(text_parts) if text_parts else f"[DOCX 无文本内容] {source}"
    except ImportError:
        return f"[DOCX 处理需要 python-docx] pip install python-docx, 文件地址: {source}"
    except Exception as e:
        return f"[DOCX 解析失败] {str(e)}, 文件地址: {source}"


def process_attachment(file_url: str, mime_type: str) -> str:
    """统一入口：处理附件

    Args:
        file_url: 附件 URL 或本地路径
        mime_type: MIME 类型，如 'image/png', 'audio/mp3', 'application/pdf'

    Returns:
        附件内容的文本描述
    """
    # 图片类型
    if mime_type.startswith("image/"):
        return process_image(file_url)

    # 音频类型
    elif mime_type.startswith("audio/"):
        return process_audio(file_url)

    # 文档类型
    elif mime_type in (
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "text/markdown",
        "text/html",
    ):
        return process_document(file_url, mime_type)

    # 视频类型 (可选)
    elif mime_type.startswith("video/"):
        return f"[视频暂不支持处理] 类型: {mime_type}, 地址: {file_url}"

    # 其他类型
    else:
        return f"[未知附件类型] {mime_type}, 地址: {file_url}"


# 便捷函数别名
extract_image_text = process_image
transcribe_audio = process_audio
extract_document_text = process_document
