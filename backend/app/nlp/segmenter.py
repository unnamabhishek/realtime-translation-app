def should_cut_segment(text: str, silence_ms: int, max_ms: int = 3000) -> bool:
    if any(text.endswith(p) for p in [".", "?", "!"]):
        return True
    if silence_ms >= 800:
        return True
    if silence_ms >= max_ms:
        return True
    return False
