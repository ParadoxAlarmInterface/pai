import codecs


class Codec(codecs.Codec):
    def encode(self, input, errors="strict"):
        return codecs.charmap_encode(input, errors, encoding_table)

    def decode(self, input, errors="strict"):
        return codecs.charmap_decode(input, errors, decoding_table)


class IncrementalEncoder(codecs.IncrementalEncoder):
    def encode(self, input, final=False):
        return codecs.charmap_encode(input, self.errors, encoding_table)[0]


class IncrementalDecoder(codecs.IncrementalDecoder):
    def decode(self, input, final=False):
        return codecs.charmap_decode(input, self.errors, decoding_table)[0]


class StreamWriter(Codec, codecs.StreamWriter):
    pass


class StreamReader(Codec, codecs.StreamReader):
    pass


def getregentry():
    return codecs.CodecInfo(
        name="paradox-ru",
        encode=Codec().encode,
        decode=Codec().decode,
        incrementalencoder=IncrementalEncoder,
        incrementaldecoder=IncrementalDecoder,
        streamreader=StreamReader,
        streamwriter=StreamWriter,
    )


### Decoding Table

# fmt: off
### Decoding Table
decoding_table = (
    "\x00"  # 0    0x00 -> NULL
    "\x01"  # 1    0x01 -> START OF HEADING
    "\x02"  # 2    0x02 -> START OF TEXT
    "\x03"  # 3    0x03 -> END OF TEXT
    "\x04"  # 4    0x04 -> END OF TRANSMISSION
    "\x05"  # 5    0x05 -> ENQUIRY
    "\x06"  # 6    0x06 -> ACKNOWLEDGE
    "\x07"  # 7    0x07 -> BELL
    "\x08"  # 8    0x08 -> BACKSPACE
    "\t"    # 9    0x09 -> HORIZONTAL TABULATION
    "\n"    # 10   0x0A -> LINE FEED
    "\x0b"  # 11   0x0B -> VERTICAL TABULATION
    "\x0c"  # 12   0x0C -> FORM FEED
    "\r"    # 13   0x0D -> CARRIAGE RETURN
    "\x0e"  # 14   0x0E -> SHIFT OUT
    "\x0f"  # 15   0x0F -> SHIFT IN
    "\x10"  # 16   0x10 -> DATA LINK ESCAPE
    "\x11"  # 17   0x11 -> DEVICE CONTROL ONE
    "\x12"  # 18   0x12 -> DEVICE CONTROL TWO
    "\x13"  # 19   0x13 -> DEVICE CONTROL THREE
    "\x14"  # 20   0x14 -> DEVICE CONTROL FOUR
    "\x15"  # 21   0x15 -> NEGATIVE ACKNOWLEDGE
    "\x16"  # 22   0x16 -> SYNCHRONOUS IDLE
    "\x17"  # 23   0x17 -> END OF TRANSMISSION BLOCK
    "\x18"  # 24   0x18 -> CANCEL
    "\x19"  # 25   0x19 -> END OF MEDIUM
    "\x1a"  # 26   0x1A -> SUBSTITUTE
    "\x1b"  # 27   0x1B -> ESCAPE
    "\x1c"  # 28   0x1C -> FILE SEPARATOR
    "\x1d"  # 29   0x1D -> GROUP SEPARATOR
    "\x1e"  # 30   0x1E -> RECORD SEPARATOR
    "\x1f"  # 31   0x1F -> UNIT SEPARATOR
    " "     # 32   0x20 -> SPACE
    "!"     # 33   0x21 -> EXCLAMATION MARK
    '"'     # 34   0x22 -> QUOTATION MARK
    "#"  # 35   0x23 -> NUMBER SIGN
    "$"  # 36   0x24 -> DOLLAR SIGN
    "%"  # 37   0x25 -> PERCENT SIGN
    "&"  # 38   0x26 -> AMPERSAND
    "'"  # 39   0x27 -> APOSTROPHE
    "("  # 40   0x28 -> LEFT PARENTHESIS
    ")"  # 41   0x29 -> RIGHT PARENTHESIS
    "*"  # 42   0x2A -> ASTERISK
    "+"  # 43   0x2B -> PLUS SIGN
    ","  # 44   0x2C -> COMMA
    "-"  # 45   0x2D -> HYPHEN-MINUS
    "."  # 46   0x2E -> FULL STOP
    "/"  # 47   0x2F -> SOLIDUS
    "0"  # 48   0x30 -> DIGIT ZERO
    "1"  # 49   0x31 -> DIGIT ONE
    "2"  # 50   0x32 -> DIGIT TWO
    "3"  # 51   0x33 -> DIGIT THREE
    "4"  # 52   0x34 -> DIGIT FOUR
    "5"  # 53   0x35 -> DIGIT FIVE
    "6"  # 54   0x36 -> DIGIT SIX
    "7"  # 55   0x37 -> DIGIT SEVEN
    "8"  # 56   0x38 -> DIGIT EIGHT
    "9"  # 57   0x39 -> DIGIT NINE
    ":"  # 58   0x3A -> COLON
    ";"  # 59   0x3B -> SEMICOLON
    "<"  # 60   0x3C -> LESS-THAN SIGN
    "="  # 61   0x3D -> EQUALS SIGN
    ">"  # 62   0x3E -> GREATER-THAN SIGN
    "?"  # 63   0x3F -> QUESTION MARK
    "@"  # 64   0x40 -> COMMERCIAL AT
    "A"  # 65   0x41 -> LATIN CAPITAL LETTER A
    "B"  # 66   0x42 -> LATIN CAPITAL LETTER B
    "C"  # 67   0x43 -> LATIN CAPITAL LETTER C
    "D"  # 68   0x44 -> LATIN CAPITAL LETTER D
    "E"  # 69   0x45 -> LATIN CAPITAL LETTER E
    "F"  # 70   0x46 -> LATIN CAPITAL LETTER F
    "G"  # 71   0x47 -> LATIN CAPITAL LETTER G
    "H"  # 72   0x48 -> LATIN CAPITAL LETTER H
    "I"  # 73   0x49 -> LATIN CAPITAL LETTER I
    "J"  # 74   0x4A -> LATIN CAPITAL LETTER J
    "K"  # 75   0x4B -> LATIN CAPITAL LETTER K
    "L"  # 76   0x4C -> LATIN CAPITAL LETTER L
    "M"  # 77   0x4D -> LATIN CAPITAL LETTER M
    "N"  # 78   0x4E -> LATIN CAPITAL LETTER N
    "O"  # 79   0x4F -> LATIN CAPITAL LETTER O
    "P"  # 80   0x50 -> LATIN CAPITAL LETTER P
    "Q"  # 81   0x51 -> LATIN CAPITAL LETTER Q
    "R"  # 82   0x52 -> LATIN CAPITAL LETTER R
    "S"  # 83   0x53 -> LATIN CAPITAL LETTER S
    "T"  # 84   0x54 -> LATIN CAPITAL LETTER T
    "U"  # 85   0x55 -> LATIN CAPITAL LETTER U
    "V"  # 86   0x56 -> LATIN CAPITAL LETTER V
    "W"  # 87   0x57 -> LATIN CAPITAL LETTER W
    "X"  # 88   0x58 -> LATIN CAPITAL LETTER X
    "Y"  # 89   0x59 -> LATIN CAPITAL LETTER Y
    "Z"  # 90   0x5A -> LATIN CAPITAL LETTER Z
    "["  # 91   0x5B -> LEFT SQUARE BRACKET
    "¥"  # 92   0x5C -> YEN
    "]"  # 93   0x5D -> RIGHT SQUARE BRACKET
    "^"  # 94   0x5E -> CIRCUMFLEX ACCENT
    "_"  # 95   0x5F -> LOW LINE
    "`"  # 96   0x60 -> GRAVE ACCENT
    "a"  # 97   0x61 -> LATIN SMALL LETTER A
    "b"  # 98   0x62 -> LATIN SMALL LETTER B
    "c"  # 99   0x63 -> LATIN SMALL LETTER C
    "d"  # 100  0x64 -> LATIN SMALL LETTER D
    "e"  # 101  0x65 -> LATIN SMALL LETTER E
    "f"  # 102  0x66 -> LATIN SMALL LETTER F
    "g"  # 103  0x67 -> LATIN SMALL LETTER G
    "h"  # 104  0x68 -> LATIN SMALL LETTER H
    "i"  # 105  0x69 -> LATIN SMALL LETTER I
    "j"  # 106  0x6A -> LATIN SMALL LETTER J
    "k"  # 107  0x6B -> LATIN SMALL LETTER K
    "l"  # 108  0x6C -> LATIN SMALL LETTER L
    "m"  # 109  0x6D -> LATIN SMALL LETTER M
    "n"  # 110  0x6E -> LATIN SMALL LETTER N
    "o"  # 111  0x6F -> LATIN SMALL LETTER O
    "p"  # 112  0x70 -> LATIN SMALL LETTER P
    "q"  # 113  0x71 -> LATIN SMALL LETTER Q
    "r"  # 114  0x72 -> LATIN SMALL LETTER R
    "s"  # 115  0x73 -> LATIN SMALL LETTER S
    "t"  # 116  0x74 -> LATIN SMALL LETTER T
    "u"  # 117  0x75 -> LATIN SMALL LETTER U
    "v"  # 118  0x76 -> LATIN SMALL LETTER V
    "w"  # 119  0x77 -> LATIN SMALL LETTER W
    "x"  # 120  0x78 -> LATIN SMALL LETTER X
    "y"  # 121  0x79 -> LATIN SMALL LETTER Y
    "z"  # 122  0x7A -> LATIN SMALL LETTER Z
    " "  # 123  0x7B -> LEFT CURLY BRACKET
    " "  # 124  0x7C -> VERTICAL LINE
    " "  # 125  0x7D -> RIGHT CURLY BRACKET
    "↲"  # 126  0x7E -> 
    " "  # 127  0x7F ->
    " "  # 128  0x80 ->
    " "  # 129  0x81 ->
    " "  # 130  0x82 ->
    " "  # 131  0x83 ->
    " "  # 132  0x84 ->
    " "  # 133  0x85 ->
    " "  # 134  0x86 ->
    " "  # 135  0x87 ->
    " "  # 136  0x88 ->
    " "  # 137  0x89 ->
    " "  # 138  0x8A ->
    " "  # 139  0x8B ->
    " "  # 140  0x8C ->
    " "  # 141  0x8D ->
    " "  # 142  0x8E ->
    " "  # 143  0x8F ->
    " "  # 144  0x90 ->
    " "  # 145  0x91 ->
    " "  # 146  0x92 ->
    " "  # 147  0x93 ->
    " "  # 148  0x94 ->
    " "  # 149  0x95 ->
    " "  # 150  0x96 ->
    " "  # 151  0x97 ->
    " "  # 152  0x98 ->
    " "  # 153  0x99 ->
    " "  # 154  0x9A ->
    " "  # 155  0x9B ->
    " "  # 156  0x9C ->
    " "  # 157  0x9D ->
    " "  # 158  0x9E ->
    " "  # 159  0x9F ->
    "Б"  # 160  0xA0 ->
    "Г"  # 161  0xA1 ->
    "Ё"  # 162  0xA2 ->
    "Ж"  # 163  0xA3 ->
    "З"  # 164  0xA4 ->
    "И"  # 165  0xA5 ->
    "Й"  # 166  0xA6 ->
    "Л"  # 167  0xA7 ->
    "П"  # 168  0xA8 ->
    "У"  # 169  0xA9 ->
    "Ф"  # 170  0xAA ->
    "Ч"  # 171  0xAB ->
    "Ш"  # 172  0xAC ->
    "Ъ"  # 173  0xAD ->
    "Ы"  # 174  0xAE ->
    "Э"  # 175  0xAF ->
    "Ю"  # 176  0xB0 ->
    "Я"  # 177  0xB1 ->
    "б"  # 178  0xB2 ->
    "в"  # 179  0xB3 ->
    "г"  # 180  0xB4 ->
    "ё"  # 181  0xB5 ->
    "ж"  # 182  0xB6 ->
    "з"  # 183  0xB7 ->
    "и"  # 184  0xB8 ->
    "й"  # 185  0xB9 ->
    "к"  # 186  0xBA ->
    "л"  # 187  0xBB ->
    "м"  # 188  0xBC ->
    "н"  # 189  0xBD ->
    "п"  # 190  0xBE ->
    "т"  # 191  0xBF ->
    "ч"  # 192  0xC0 ->
    "ш"  # 193  0xC1 ->
    "ъ"  # 194  0xC2 ->
    "ы"  # 195  0xC3 ->
    "ь"  # 196  0xC4 ->
    "э"  # 197  0xC5 ->
    "ю"  # 198  0xC6 ->
    "я"  # 199  0xC7 ->
    " "  # 200  0xC8 ->
    " "  # 201  0xC9 ->
    " "  # 202  0xCA ->
    " "  # 203  0xCB ->
    " "  # 204  0xCC ->
    " "  # 205  0xCD ->
    " "  # 206  0xCE ->
    " "  # 207  0xCF ->
    " "  # 208  0xD0 ->
    " "  # 209  0xD1 ->
    " "  # 210  0xD2 ->
    " "  # 211  0xD3 ->
    " "  # 212  0xD4 ->
    " "  # 213  0xD5 ->
    " "  # 214  0xD6 ->
    " "  # 215  0xD7 ->
    " "  # 216  0xD8 ->
    " "  # 217  0xD9 ->
    " "  # 218  0xDA ->
    " "  # 219  0xDB ->
    " "  # 220  0xDC ->
    " "  # 221  0xDD ->
    " "  # 222  0xDE ->
    " "  # 223  0xDF ->
    "Д"  # 224  0xE0 ->
    "Ц"  # 225  0xE1 ->
    "Щ"  # 226  0xE2 ->
    "д"  # 227  0xE3 ->
    "ф"  # 228  0xE4 ->
    "ц"  # 229  0xE5 ->
    "щ"  # 230  0xE6 ->
    " "  # 231  0xE7 ->
    " "  # 232  0xE8 ->
    " "  # 233  0xE9 ->
    " "  # 234  0xEA ->
    " "  # 235  0xEB ->
    " "  # 236  0xEC ->
    " "  # 237  0xED ->
    " "  # 238  0xEE ->
    " "  # 239  0xEF ->
    " "  # 240  0xF0 ->
    " "  # 241  0xF1 ->
    " "  # 242  0xF2 ->
    " "  # 243  0xF3 ->
    " "  # 244  0xF4 ->
    " "  # 245  0xF5 ->
    " "  # 246  0xF6 ->
    " "  # 247  0xF7 ->
    " "  # 248  0xF8 ->
    " "  # 249  0xF9 ->
    " "  # 250  0xFA ->
    " "  # 251  0xFB ->
    " "  # 252  0xFC ->
    " "  # 253  0xFD ->
    " "  # 254  0xFE ->
    " "  # 255  0xFF ->
)

encoding_table = codecs.charmap_build(decoding_table)
