"""Chapter body length contract; Python iteration counts Unicode code points.

Whitespace is excluded; punctuation, digits and letters count. Titles are never
passed to these helpers. Integer arithmetic keeps the inclusive 10% bounds exact.
"""

COUNTING_METHOD = "non_whitespace_codepoints"


def count_body_words(content: str) -> int:
    return sum(not character.isspace() for character in content)


def word_bounds(target_words: int) -> tuple[int, int]:
    return (target_words * 9 + 9) // 10, target_words * 11 // 10


def scene_count(target_words: int) -> int:
    """Fixed call bound for a chapter; API targets are between 300 and 6000."""
    return min(8, (target_words + 799) // 800)


def next_scene_budget(target_words: int, actual_words: int, remaining: int) -> int:
    """Bounded guidance redistributed from actual output, never a hard limit."""
    return max(200, min(target_words, (target_words - actual_words + remaining - 1) // remaining))


def require_replacements(value, count: int) -> dict[int, str]:
    """A listed ID replaces its whole section; an absent ID stays untouched."""
    if not isinstance(value, list):
        raise ValueError("模型返回的分节列表格式不正确；未保存本章，请重试")
    entries = {}
    for item in value:
        if (not isinstance(item, dict) or set(item) != {"id", "content"} or
                type(item["id"]) is not int or not 1 <= item["id"] <= count or item["id"] in entries or
                not isinstance(item["content"], str) or not item["content"].strip()):
            raise ValueError("模型返回的分节编号或正文无效、重复或不完整；未保存本章，请重试")
        entries[item["id"]] = item["content"]
    return entries


def require_word_range(content: str, target_words: int) -> int:
    actual = count_body_words(content)
    minimum, maximum = word_bounds(target_words)
    if not minimum <= actual <= maximum:
        raise ValueError(f"章节正文字数不达标：目标 {target_words} 字，实际 {actual} 字，允许 {minimum}–{maximum} 字（不含空白和标题）；未保存本章，请重试")
    return actual
