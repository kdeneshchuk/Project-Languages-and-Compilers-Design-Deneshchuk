"""Telly lexer: a hand-written state machine over bytes."""


class CompileError(Exception):
    pass


class Token:
    def __init__(self, kind, text, line, col):
        self.kind = kind
        self.text = text
        self.line = line
        self.col = col

    def __repr__(self):
        return f"Token({self.kind!r}, {self.text!r}, {self.line}, {self.col})"


# word -> token kind
WORDS = {
    "always": "kw", "once": "kw", "changing": "kw",
    "is": "kw", "was": "kw", "became": "kw",
    "when": "kw", "otherwise": "kw", "end": "kw", "tell": "kw",
    "int": "type", "long": "type", "flag": "type",
    "yes": "bool", "no": "bool",
    "equals": "cmp", "differs": "cmp",
}

# the four emoji tokens: byte sequence -> (kind, text)
EMOJI = {
    b"\xf0\x9f\x91\x8d": ("bool", "\U0001F44D"),  # thumbs up
    b"\xf0\x9f\x91\x8e": ("bool", "\U0001F44E"),  # thumbs down
    b"\xf0\x9f\x9f\xb0": ("cmp", "\U0001F7F0"),   # heavy equals sign
    b"\xf0\x9f\x9a\xab": ("cmp", "\U0001F6AB"),   # prohibited
}

# single-byte tokens: byte value -> kind
SYMBOLS = {
    ord("+"): "op", ord("-"): "op", ord("*"): "op",
    ord(":"): "colon", ord("."): "dot",
}

MAX_LONG = 9223372036854775807


def is_alpha(b):
    return b is not None and (65 <= b <= 90 or 97 <= b <= 122 or b == 95)


def is_digit(b):
    return b is not None and 48 <= b <= 57


def describe_byte(b):
    if 32 < b < 127:
        return repr(chr(b))
    return f"0x{b:02X}"


def lex(data: bytes):
    """Return a flat list of tokens. Columns are 1-based and count bytes."""
    tokens = []
    state, start = "START", 0
    sline, scol = 1, 1          # position of the first byte of the current token
    line, col = 1, 1
    i = 0

    while i <= len(data):       # one extra step: the end of input
        b = data[i] if i < len(data) else None

        if state == "START":
            if b is None:
                break
            elif b in (32, 9, 13):          # space, tab, CR
                pass
            elif b == 10:                    # newline
                line += 1
                col = 0
            elif is_alpha(b):
                state, start, sline, scol = "IDENT", i, line, col
            elif is_digit(b):
                state, start, sline, scol = "NUMBER", i, line, col
            elif b in SYMBOLS:
                tokens.append(Token(SYMBOLS[b], chr(b), line, col))
            elif b == 0xF0:                  # first byte of a 4-byte emoji
                state, start, sline, scol = "EMOJI", i, line, col
            else:
                raise CompileError(f"line {line}:{col}: unexpected byte {describe_byte(b)}")

        elif state == "IDENT":
            if is_alpha(b) or is_digit(b):
                pass
            else:
                word = data[start:i].decode()
                tokens.append(Token(WORDS.get(word, "ident"), word, sline, scol))
                state = "START"
                continue                     # re-read this byte in START

        elif state == "NUMBER":
            if is_digit(b):
                pass
            elif is_alpha(b):
                raise CompileError(
                    f"line {sline}:{scol}: a letter or '_' directly after digits")
            else:
                word = data[start:i].decode()
                if int(word) > MAX_LONG:
                    raise CompileError(
                        f"line {sline}:{scol}: number {word} does not fit in long")
                tokens.append(Token("number", word, sline, scol))
                state = "START"
                continue

        elif state == "EMOJI":
            if b is not None and 0x80 <= b <= 0xBF:
                if i - start == 3:           # the fourth byte has arrived
                    seq = data[start:i + 1]
                    if seq not in EMOJI:
                        raise CompileError(f"line {sline}:{scol}: unknown emoji")
                    kind, text = EMOJI[seq]
                    tokens.append(Token(kind, text, sline, scol))
                    state = "START"
            else:
                raise CompileError(f"line {sline}:{scol}: incomplete or unknown emoji")

        i += 1
        col += 1

    return tokens
