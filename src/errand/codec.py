from typing import Any

import msgspec


def enc_hook(value: Any) -> Any:
    """msgspec 不认识的对象, 有 model_dump 的交给它自己导出"""

    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    raise TypeError(f"无法编码 {type(value).__name__}")


def dec_hook(kind: Any, value: Any) -> Any:
    """msgspec 不认识的类型, 有 model_validate 的交给它自己还原"""

    if hasattr(kind, "model_validate"):
        return kind.model_validate(value)
    raise TypeError(f"无法解码为 {kind}")


def encode(value: Any) -> str:
    return msgspec.json.encode(value, enc_hook=enc_hook).decode()


def decode(raw: str, kind: Any) -> Any:
    """按类型把 JSON 文本还原成对象, 不符合类型时抛出 msgspec.ValidationError"""

    return msgspec.json.decode(raw, type=kind, dec_hook=dec_hook)
