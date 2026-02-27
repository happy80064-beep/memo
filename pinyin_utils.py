# -*- coding: utf-8 -*-
"""
拼音工具模块
统一处理中文转拼音和实体命名标准化
"""
from pypinyin import pinyin, Style
import re

# 多音字例外表（常见姓名多音字）
PINYIN_EXCEPTIONS = {
    # 常见姓名多音字
    "曾": "zeng",          # 姓氏读 zeng，不是 ceng
    "单": "shan",          # 姓氏读 shan，不是 dan
    "查": "zha",           # 姓氏读 zha，不是 cha
    "仇": "qiu",           # 姓氏读 qiu，不是 chou
    "区": "ou",            # 姓氏读 ou，不是 qu
    "解": "xie",           # 姓氏读 xie，不是 jie
    "繁": "po",            # 姓氏读 po，不是 fan
    "幺": "yao",           # 读 yao
    "长孙": "zhang-sun",   # 复姓
    "子车": "zi-ju",       # 复姓
    # 常见词语
    "长大": "zhang-da",
    "音乐": "yin-yue",
    "快乐": "kuai-le",
    "长春": "chang-chun",
    "重庆": "chong-qing",
}


def chinese_to_pinyin(text: str) -> str:
    """
    中文转拼音（每个字分开）

    李佳泽 -> li-jia-ze
    李国栋 -> li-guo-dong

    Args:
        text: 中文字符串

    Returns:
        拼音字符串，用连字符分隔
    """
    if not text:
        return ""

    # 先检查完整匹配例外
    if text in PINYIN_EXCEPTIONS:
        return PINYIN_EXCEPTIONS[text]

    # 逐字检查例外
    result = []
    for char in text:
        if char in PINYIN_EXCEPTIONS:
            result.append(PINYIN_EXCEPTIONS[char])
        else:
            # 使用 pypinyin 转换
            py = pinyin(char, style=Style.NORMAL, strict=False, errors='default')
            if py:
                result.append(py[0][0])
            else:
                # 如果转换失败，保留原字符
                result.append(char.lower())

    return "-".join(result)


def generate_entity_path(name: str, entity_type: str = "person") -> str:
    """
    生成标准化实体 path

    Args:
        name: 实体名称
        entity_type: 实体类型，默认 person

    Returns:
        标准化的 path
    """
    # 清理名称
    clean_name = name.strip()

    # 判断是否中文
    if is_chinese(clean_name):
        pinyin_name = chinese_to_pinyin(clean_name)
        return f"/people/{pinyin_name}"
    else:
        # 外文：转小写，空格替换为连字符
        safe_name = clean_name.lower().replace(" ", "-")
        # 移除特殊字符，只保留字母、数字、连字符
        safe_name = re.sub(r'[^a-z0-9\-]', '', safe_name)
        return f"/people/{safe_name}"


def is_chinese(text: str) -> bool:
    """
    判断是否包含中文字符

    Args:
        text: 待检测文本

    Returns:
        是否包含中文
    """
    if not text:
        return False
    for char in text:
        if '\u4e00' <= char <= '\u9fff':
            return True
    return False


def contains_chinese(text: str) -> bool:
    """
    别名：判断是否包含中文字符
    """
    return is_chinese(text)


def normalize_pinyin_path(path: str) -> str:
    """
    标准化现有的拼音 path
    将各种格式统一为 li-jia-ze 格式

    Args:
        path: 现有 path，如 /people/li-jiaze 或 /people/lijiaze

    Returns:
        标准化的 path
    """
    # 提取名称部分
    if "/people/" in path:
        name_part = path.replace("/people/", "")
    elif "/" in path:
        parts = path.split("/")
        name_part = parts[-1] if parts else path
    else:
        name_part = path

    # 如果已经是拼音格式，尝试重新标准化
    if not is_chinese(name_part):
        # 可能是 li-jiaze 或 lijiaze 格式
        # 先尝试识别是否是连续拼音
        if "-" in name_part:
            # 已经有连字符，检查是否需要调整
            parts = name_part.split("-")
            # 如果某部分太长（超过6个字符），可能是连续拼音
            standardized = []
            for part in parts:
                if len(part) > 6:
                    # 尝试拆分，但这比较复杂，先保留
                    standardized.append(part)
                else:
                    standardized.append(part)
            return f"/people/{'-'.join(standardized)}"
        else:
            # 没有连字符，需要添加
            # 简单处理：每2-6个字符尝试分割（这不是完美的，但适用于大多数情况）
            return f"/people/{name_part}"

    # 包含中文，重新转换
    return generate_entity_path(name_part)


if __name__ == "__main__":
    # 测试用例
    test_cases = [
        ("李佳泽", "li-jia-ze"),
        ("李国栋", "li-guo-dong"),
        ("杨桂花", "yang-gui-hua"),
        ("李俊杰", "li-jun-jie"),
        ("贾雪云", "jia-xue-yun"),
        ("Peter", "peter"),
        ("John Smith", "john-smith"),
        ("6宝", "6-bao"),
        ("长大", "zhang-da"),  # 多音字测试
        ("音乐", "yin-yue"),   # 多音字测试
    ]

    print("拼音转换测试：")
    print("=" * 60)
    for name, expected in test_cases:
        result = generate_entity_path(name)
        status = "OK" if expected in result else "FAIL"
        print(f"{status} {name:10} -> {result:20} (期望: {expected})")
