import re
from typing import Callable


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_float(text: str) -> float | None:
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(m.group(0)) if m else None


def parse_int(text: str) -> int | None:
    m = re.search(r"\d+", text)
    return int(m.group(0)) if m else None


def parse_percent(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    return float(m.group(1)) / 100.0 if m else None


def parse_range(text: str) -> tuple[float, float] | None:
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)]
    if len(nums) >= 2:
        return (min(nums[0], nums[1]), max(nums[0], nums[1]))
    return None


def parse_split(text: str, conv: Callable[[str], float | int]) -> list:
    return [conv(x) for x in re.findall(r"-?\d+(?:\.\d+)?", text)]


def normalize_ip(text: str) -> str | None:
    m = re.search(r"IP\s*\d{2,3}", clean(text))
    return m.group(0).replace(" ", "").upper() if m else None


def normalize_surge(text: str) -> str:
    t = clean(text).upper().replace("TYPE", "Type")
    pairs = []
    for m in re.finditer(r"(DC|AC)\s*(?:Type\s*)?([IVX]+)|Type\s*([IVX]+)[^,|/]*?\(?(DC|AC)", t):
        if m.group(1) and m.group(2):
            pairs.append((m.group(1), m.group(2)))
        elif m.group(4) and m.group(3):
            pairs.append((m.group(4), m.group(3)))
    if not pairs:
        return t
    return ", ".join(sorted(f"{side} Type {level}" for side, level in pairs))

def normalize_noise(text: str) -> str:
    return clean(text).replace("dB", "").replace(" ", "").strip()

_STANDARD_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9/ .\-]*\d[A-Za-z0-9/ .\-]*")

def parse_standards(text: str) -> list[str]:
    codes = []
    for m in _STANDARD_RE.finditer(clean(text)):
        code = re.sub(r"\s+", " ", m.group(0)).strip(" ,;").rstrip(",")
        if code and code not in codes:
            codes.append(code)
    return codes


HANDLERS = {
    "float": parse_float,
    "int": parse_int,
    "percent": parse_percent,
    "range": parse_range,
    "split_float": lambda s: parse_split(s, float),
    "split_int": lambda s: parse_split(s, int),
    "ip": normalize_ip,
    "surge": normalize_surge,
    "noise": normalize_noise,
    "standards": lambda s: parse_standards(s),
    "text": clean,
}


def normalize(value_type: str, raw: str) -> tuple[object | None, str]:
    fn = HANDLERS[value_type]
    try:
        value = fn(raw)
    except (ValueError, re.error):
        return None, f"parse failed for {value_type!r}: {raw!r}"
    if value is None:
        return None, f"no {value_type} value found in {raw!r}"
    return value, ""