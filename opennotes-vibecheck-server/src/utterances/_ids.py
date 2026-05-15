import hashlib
import re


def _norm_ws(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def stable_utterance_id(kind: str, text: str, global_offset: int, ordinal: int) -> str:
    key = f"{kind}\x00{_norm_ws(text)}\x00{global_offset}\x00{ordinal}"
    digest = hashlib.blake2s(key.encode(), digest_size=8).hexdigest()
    return f"{kind}-{digest}"
