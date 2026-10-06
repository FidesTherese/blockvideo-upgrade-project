"""Split a Japanese request into clauses so each statement is read on its own.

"話速を1.2倍にして動画は生成しないで" holds two statements: a request about speed
and a negation about generation. Guards that look for numbers, directions or
negations read one clause at a time so one statement never colours another.
"""
from __future__ import annotations

import re
import unicodedata

# A te-form request ends a clause unless it continues into a polite negation
# ("止めていただかなくていい") or a request ending ("してください").
_TE = r"して|って|んで|いて|えて|けて|せて|めて|べて|れて|きて|みて|ちて"
_CONTINUES = r"いただかな|もらわな|くれな|ほしくな|ください|ほしい|から|も"
_BOUNDARY = rf"[、。,!！?？\n]|\.(?!\d)|(?<=てから)|(?<=うえで)|(?<=上で)|(?:(?<=して)|(?<=って)|(?<=んで)|(?<=いて)|(?<=えて)|(?<=けて)|(?<=せて)|(?<=めて)|(?<=べて)|(?<=れて)|(?<=きて)|(?<=みて)|(?<=ちて)|(?<=ないで))(?!{_CONTINUES})"


def normalized(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def clauses(text: str) -> list[str]:
    """Non-empty clauses of normalized text, in order."""
    return [part.strip() for part in re.split(_BOUNDARY, normalized(text)) if part and part.strip()]
