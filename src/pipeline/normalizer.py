from typing import Callable


def clean(text: str) -> str:
    return " ".join(text.split())


def _extract_number(text: str, start: int, allow_sign: bool = True) -> tuple[str, int] | None:
    """Extract a number starting at text[start]. Returns (num_str, next_index) or None."""
    i = start
    n = len(text)
    if i >= n:
        return None
    if allow_sign and text[i] in ("+", "-"):
        i += 1
    if i >= n or not text[i].isdigit():
        return None
    j = i
    while j < n and text[j].isdigit():
        j += 1
    if j < n and text[j] == ".":
        k = j + 1
        if k < n and text[k].isdigit():
            while k < n and text[k].isdigit():
                k += 1
            return text[start:k], k
    return text[start:j], j


def _find_all_numbers(text: str, allow_sign: bool = True) -> list[str]:
    """Find all numbers in text."""
    results = []
    i, n = 0, len(text)
    while i < n:
        if text[i].isdigit() or (allow_sign and text[i] in ("+", "-") and i + 1 < n and text[i + 1].isdigit()):
            r = _extract_number(text, i, allow_sign=allow_sign)
            if r:
                num_str, next_i = r
                results.append(num_str)
                i = next_i
                continue
        i += 1
    return results


def parse_float(text: str) -> float | None:
    nums = _find_all_numbers(text, allow_sign=True)
    return float(nums[0]) if nums else None


def parse_int(text: str) -> int | None:
    nums = _find_all_numbers(text, allow_sign=False)
    return int(nums[0]) if nums else None


def parse_percent(text: str) -> float | None:
    idx = text.find("%")
    if idx < 0:
        return None
    # scan backwards from before the % for digits, optional dot, more digits
    j = idx - 1
    while j >= 0 and text[j] == " ":
        j -= 1
    if j < 0 or not text[j].isdigit():
        return None
    end = j + 1
    while j >= 0 and text[j].isdigit():
        j -= 1
    if j >= 0 and text[j] == ".":
        dot = j
        j -= 1
        if j >= 0 and text[j].isdigit():
            while j >= 0 and text[j].isdigit():
                j -= 1
            num_str = text[j + 1:end]
        else:
            num_str = text[dot:end]
    else:
        num_str = text[j + 1:end]
    return float(num_str) / 100.0


def parse_range(text: str) -> tuple[float, float] | None:
    nums = [float(x) for x in _find_all_numbers(text, allow_sign=False)]
    if len(nums) >= 2:
        return (min(nums[0], nums[1]), max(nums[0], nums[1]))
    return None


def parse_split(text: str, conv: Callable[[str], float | int]) -> list:
    return [conv(x) for x in _find_all_numbers(text, allow_sign=True)]


def normalize_ip(text: str) -> str | None:
    t = clean(text).upper()
    idx = t.find("IP")
    if idx < 0:
        return None
    j = idx + 2
    # skip optional spaces between IP and digits
    while j < len(t) and t[j] == " ":
        j += 1
    if j >= len(t) or not t[j].isdigit():
        return None
    start = j
    while j < len(t) and t[j].isdigit():
        j += 1
    digit_count = j - start
    if digit_count < 2 or digit_count > 3:
        return None
    return t[idx:j].replace(" ", "")


def normalize_surge(text: str) -> str:
    t = clean(text).upper().replace("TYPE", "Type")
    pairs = []
    # Scan for patterns: "DC Type IV", "AC Type II", "Type II(DC)", "Type II(AC)"
    i = 0
    while i < len(t):
        side = None
        level = None
        if t[i:i+2] in ("DC", "AC") and i + 2 < len(t) and t[i+2] in (" ", "T"):
            side = t[i:i+2]
            rest = t[i+2:].lstrip()
            if rest.startswith("Type"):
                rest = rest[4:].lstrip()
                level = ""
                j = 0
                while j < len(rest) and rest[j] in "IVX":
                    level += rest[j]
                    j += 1
        elif t[i:].startswith("Type "):
            rest = t[i+5:].lstrip()
            level = ""
            j = 0
            while j < len(rest) and rest[j] in "IVX":
                level += rest[j]
                j += 1
            rest = rest[j:].lstrip()
            if rest.startswith("(") and len(rest) > 2:
                paren_end = rest.find(")")
                if paren_end > 0:
                    side = rest[1:paren_end]
        if side and level:
            pairs.append((side, level))
        i += 1
    if not pairs:
        return t
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for pair in pairs:
        if pair not in seen:
            seen.add(pair)
            unique.append(pair)
    return ", ".join(sorted(f"{side} Type {level}" for side, level in unique))


def normalize_noise(text: str) -> str:
    return clean(text).replace("dB", "").replace(" ", "").strip()


def _is_standard_token(s: str) -> bool:
    """Check if s looks like a standard code: starts with letter, contains at least one digit."""
    if not s or not s[0].isalpha():
        return False
    return any(ch.isdigit() for ch in s)


def parse_standards(text: str) -> list[str]:
    tokens = clean(text).split(",")
    codes = []
    for token in tokens:
        parts = token.strip().split()
        # reconstruct multi-word standard codes like "IEC 61727" or "VDE-AR-N 4105"
        if not parts:
            continue
        # try progressively longer prefixes
        best = None
        for end in range(1, len(parts) + 1):
            candidate = " ".join(parts[:end])
            if _is_standard_token(candidate):
                best = candidate
        if best and best not in codes:
            codes.append(best)
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
    except (ValueError, KeyError):
        return None, f"parse failed for {value_type!r}: {raw!r}"
    if value is None:
        return None, f"no {value_type} value found in {raw!r}"
    return value, ""
