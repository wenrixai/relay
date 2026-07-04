"""Vendored pure-Python smaz codec (antirez/smaz), byte-oriented (§8.4, D3).

Vendored rather than depended on: PyPI bindings are unmaintained or need C toolchains the
Alpine image avoids. PII fields are short strings, so pure Python is fast enough. The
codebook is frozen — changing any entry breaks decompression of outstanding tokens (the
pinned-vector tests guard this).

Wire format (canonical smaz): bytes 0-253 index the codebook; 254 escapes one verbatim
byte; 255 is followed by ``length - 1`` and that many verbatim bytes.
"""

from __future__ import annotations

_CODEBOOK: tuple[bytes, ...] = tuple(
    entry.encode("latin-1")
    for entry in (
        " ",
        "the",
        "e",
        "t",
        "a",
        "of",
        "o",
        "and",
        "i",
        "n",
        "s",
        "e ",
        "r",
        " th",
        " t",
        "in",
        "he",
        "th",
        "h",
        "he ",
        "to",
        "\r\n",
        "l",
        "s ",
        "d",
        " a",
        "an",
        "er",
        "c",
        " o",
        "d ",
        "on",
        " of",
        "re",
        "of ",
        "t ",
        ", ",
        "is",
        "u",
        "at",
        "   ",
        "n ",
        "or",
        "which",
        "f",
        "m",
        "as",
        "it",
        "that",
        "\n",
        "was",
        "en",
        "  ",
        " w",
        "es",
        " an",
        " i",
        "\r",
        "f ",
        "g",
        "p",
        "nd",
        " s",
        "nd ",
        "ed ",
        "w",
        "ed",
        "http://",
        "for",
        "te",
        "ing",
        "y ",
        "The",
        " c",
        "ti",
        "r ",
        "his",
        "st",
        " in",
        "ar",
        "nt",
        ",",
        " to",
        "y",
        "ng",
        " h",
        "with",
        "le",
        "al",
        "to ",
        "b",
        "ou",
        "be",
        "were",
        " b",
        "se",
        "o ",
        "ent",
        "ha",
        "ng ",
        "their",
        '"',
        "hi",
        "from",
        " f",
        "in ",
        "de",
        "ion",
        "me",
        "v",
        ".",
        "ve",
        "all",
        "re ",
        "ri",
        "ro",
        "is ",
        "co",
        "f t",
        "are",
        "ea",
        ". ",
        "her",
        " m",
        "er ",
        " p",
        "es ",
        "by",
        "they",
        "di",
        "ra",
        "ic",
        "not",
        "s, ",
        "d t",
        "at ",
        "ce",
        "la",
        "h ",
        "ne",
        "as ",
        "tio",
        "on ",
        "n t",
        "io",
        "we",
        " a ",
        "om",
        ", a",
        "s o",
        "ur",
        "li",
        "ll",
        "ch",
        "had",
        "this",
        "e t",
        "g ",
        "e\r\n",
        " wh",
        "ere",
        " co",
        "e o",
        "a ",
        "us",
        " d",
        "ss",
        "\n\r\n",
        "\r\n\r",
        '="',
        " be",
        " e",
        "s a",
        "ma",
        "one",
        "t t",
        "or ",
        "but",
        "el",
        "so",
        "l ",
        "e s",
        "s,",
        "no",
        "ter",
        " wa",
        "iv",
        "ho",
        "e a",
        " r",
        "hat",
        "s t",
        "ns",
        "ch ",
        "wh",
        "tr",
        "ut",
        "/",
        "have",
        "ly ",
        "ta",
        " ha",
        " on",
        "tha",
        "-",
        " l",
        "ati",
        "en ",
        "pe",
        " re",
        "there",
        "ass",
        "si",
        " fo",
        "wa",
        "ec",
        "our",
        "who",
        "its",
        "z",
        "fo",
        "rs",
        ">",
        "ot",
        "un",
        "<",
        "im",
        "th ",
        "nc",
        "ate",
        "><",
        "ver",
        "ad",
        " we",
        "ly",
        "ee",
        " n",
        "id",
        " cl",
        "ac",
        "il",
        "</",
        "rt",
        " wi",
        "div",
        "e, ",
        " it",
        "whi",
        " ma",
        "ge",
        "x",
        "e c",
        "men",
        ".com",
    )
)

_ENCODE: dict[bytes, int] = {entry: code for code, entry in enumerate(_CODEBOOK)}
_MAX_ENTRY = max(len(entry) for entry in _CODEBOOK)

_ESCAPE_ONE = 254
_ESCAPE_MANY = 255
_MAX_VERBATIM = 256


def _flush_verbatim(out: bytearray, verbatim: bytearray) -> None:
    while verbatim:
        chunk, rest = verbatim[:_MAX_VERBATIM], verbatim[_MAX_VERBATIM:]
        if len(chunk) == 1:
            out.append(_ESCAPE_ONE)
        else:
            out.append(_ESCAPE_MANY)
            out.append(len(chunk) - 1)
        out.extend(chunk)
        verbatim = rest


def compress(data: bytes) -> bytes:
    """smaz-compress ``data`` (greedy longest codebook match, verbatim escapes)."""
    out = bytearray()
    verbatim = bytearray()
    position = 0
    while position < len(data):
        code: int | None = None
        length = 0
        for length in range(min(_MAX_ENTRY, len(data) - position), 0, -1):
            code = _ENCODE.get(data[position : position + length])
            if code is not None:
                break
        if code is not None:
            _flush_verbatim(out, verbatim)
            verbatim = bytearray()
            out.append(code)
            position += length
        else:
            verbatim.append(data[position])
            position += 1
    _flush_verbatim(out, verbatim)
    return bytes(out)


def decompress(data: bytes) -> bytes:
    """Reverse :func:`compress`.

    Raises:
        ValueError: truncated escape sequences (corrupt input).
    """
    out = bytearray()
    position = 0
    while position < len(data):
        byte = data[position]
        if byte == _ESCAPE_ONE:
            if position + 1 >= len(data):
                raise ValueError("smaz: truncated single-byte escape")
            out.append(data[position + 1])
            position += 2
        elif byte == _ESCAPE_MANY:
            if position + 1 >= len(data):
                raise ValueError("smaz: truncated run-length escape")
            length = data[position + 1] + 1
            chunk = data[position + 2 : position + 2 + length]
            if len(chunk) != length:
                raise ValueError("smaz: truncated verbatim run")
            out.extend(chunk)
            position += 2 + length
        else:
            out.extend(_CODEBOOK[byte])
            position += 1
    return bytes(out)
