"""统一校验高速版的目标数据来源开关。"""


VALID_TARGET_SOURCES = {"matlab", "manual"}


def validate_target_source(source: str) -> str:
    value = str(source).strip().lower()
    if value not in VALID_TARGET_SOURCES:
        raise ValueError(
            f"TARGET_SOURCE 必须是 'matlab' 或 'manual'，当前值为：{source!r}"
        )
    return value
