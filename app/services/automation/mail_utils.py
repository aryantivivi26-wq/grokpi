import re
from typing import Optional


# Common false-positive words (CSS/HTML/page chrome)
_FALSE_POSITIVES = {
    "SCRIPT", "IFRAME", "BUTTON", "CLICKS", "MAILTO", "HTTPS",
    "GOOGLE", "VERIFY", "CHROME", "WINDOW", "MARGIN", "BORDER",
    "WEBKIT", "INLINE", "HEADER", "FOOTER", "CENTER", "BUYAPP",
    "RETURN", "SCREEN", "SCROLL", "HIDDEN", "NORMAL", "ITALIC",
    "FAMILY", "WEIGHT", "STYLES", "IMAGES", "COLORS", "LAYOUT",
    "MOBILE", "PLUGIN", "COOKIE", "ACCEPT", "RELOAD", "SUBMIT",
    "DELETE", "CANCEL", "SEARCH", "DOMAIN", "SERVER", "IMPORT",
    "FILTER", "EXPAND", "TOGGLE", "OBJECT", "STRING", "MASTER",
    "SELECT", "INSERT", "UPDATE", "RANDOM", "EXPORT", "MODULE",
    "STATIC", "PUBLIC",
}


def extract_verification_code(text: str) -> Optional[str]:
    """Extract verification code from text (email body or plain text).

    Gemini Enterprise uses 6-char uppercase alphanumeric codes like YGCRAS.
    """
    if not text:
        return None

    # 1: Context match — "verification code is: XXXXXX"
    context_patterns = [
        r"(?:verification|Verifikasi)\s+code\s+is[:\s.]+([A-Za-z0-9]{5,8})\b",
        r"(?:code|kode|OTP|passcode|pin)[:\s：]+([A-Za-z0-9]{5,8})\b",
    ]
    for pattern in context_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = match.group(1).upper()
            if candidate not in _FALSE_POSITIVES and not re.match(
                r"^\d+(?:px|pt|em|rem|vh|vw|%)$", candidate, re.IGNORECASE
            ):
                return candidate

    # 2: Standalone 6-char alphanumeric (strict)
    for m in re.finditer(r"\b([A-Z0-9]{6})\b", text):
        candidate = m.group(1)
        if candidate not in _FALSE_POSITIVES:
            return candidate

    # 3: 6-digit numeric fallback
    digits = re.findall(r"\b\d{6}\b", text)
    if digits:
        return digits[0]

    return None
