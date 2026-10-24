#!/usr/bin/env python3
"""
Convert Shinonome (東雲) 16-dot BDF fonts into C arrays for the AQM1248A LCD.

The BDF bitmaps are stored row by row (horizontal scan). The AQM1248A
(ST7565R) display RAM is organized in "pages": each data byte written to the
LCD is a vertical strip of 8 pixels, bit 0 at the top. This script transposes
every glyph into that page/column layout so that the firmware can send a
glyph to the LCD directly from flash with spi_write_blocking(), without any
bit manipulation at run time.

Glyph layout (width W = 16 for full-width, 8 for half-width):
    glyph[0     .. W-1 ]: page 0 (rows 0-7),  one byte per column
    glyph[W     .. 2W-1]: page 1 (rows 8-15), one byte per column
    bit n of each byte  : row (page * 8 + n)

Full-width glyphs are looked up by Unicode code point through a sorted key
table (binary search). Half-width glyphs (ASCII and half-width Katakana) are
looked up directly by index.

Usage:
    python3 tools/bdf2c.py \\
        --kanji fonts/shinonome-0.9.11/bdf/shnmk16.bdf \\
        --ascii fonts/shinonome-0.9.11/bdf/shnm8x16a.bdf \\
        --kana  fonts/shinonome-0.9.11/bdf/shnm8x16r.bdf \\
        --out-dir .
"""

import argparse
import os
import sys

FONT_HEIGHT = 16
PAGES = FONT_HEIGHT // 8

# Half-width ranges (encoding in the BDF file)
ASCII_FIRST, ASCII_LAST = 0x20, 0x7E        # shnm8x16a.bdf (ISO8859-1)
KANA_FIRST, KANA_LAST = 0xA1, 0xDF          # shnm8x16r.bdf (JIS X 0201)
KANA_UNICODE_FIRST = 0xFF61                 # U+FF61 HALFWIDTH IDEOGRAPHIC FULL STOP

# Full-width substitute for characters that are not in the font
GETA_JIS = 0x222E                           # '〓' (2-14)


def parse_bdf(path):
    """Return {encoding: (width, height, xoff, yoff, [row bits as int])}."""
    glyphs = {}
    with open(path, encoding="latin-1") as f:
        lines = iter(f.read().splitlines())
    for line in lines:
        if not line.startswith("STARTCHAR"):
            continue
        encoding = None
        bbx = None
        rows = []
        for line in lines:
            if line.startswith("ENCODING"):
                encoding = int(line.split()[1])
            elif line.startswith("BBX"):
                bbx = tuple(int(v) for v in line.split()[1:5])
            elif line.startswith("BITMAP"):
                for line in lines:
                    if line.startswith("ENDCHAR"):
                        break
                    rows.append(int(line, 16))
                break
        if encoding is None or bbx is None or encoding < 0:
            continue
        w, h, _, _ = bbx
        nbytes = (w + 7) // 8
        # left-align the row bits to the bounding box width
        rows = [r >> (nbytes * 8 - w) for r in rows]
        glyphs[encoding] = (w, h, rows)
    return glyphs


def to_lcd_pages(w, h, rows, cell_width):
    """Transpose a horizontal-scan glyph into LCD page/column bytes."""
    if h != FONT_HEIGHT or w != cell_width:
        raise ValueError("unexpected glyph size %dx%d" % (w, h))
    out = bytearray(cell_width * PAGES)
    for page in range(PAGES):
        for x in range(cell_width):
            b = 0
            for bit in range(8):
                y = page * 8 + bit
                if (rows[y] >> (cell_width - 1 - x)) & 1:
                    b |= 1 << bit
            out[page * cell_width + x] = b
    return bytes(out)


def jis_to_unicode(jis):
    """Return the Unicode code points that map to a JIS X 0208 code.

    EUC-JP and CP932 disagree on a few characters (e.g. U+301C/U+FF5E,
    U+2212/U+FF0D), so both are registered to accept either form.
    """
    ku, ten = (jis >> 8) - 0x20, (jis & 0xFF) - 0x20
    euc = bytes([(jis >> 8) | 0x80, (jis & 0xFF) | 0x80])
    # JIS -> Shift_JIS
    s1 = (ku + 0x101) // 2 if ku <= 62 else (ku + 0x181) // 2
    s2 = ten + (0x3F if ku % 2 else 0x9E)
    if ku % 2 and ten >= 64:
        s2 += 1
    sjis = bytes([s1, s2])

    cps = []
    for data, codec in ((euc, "euc_jp"), (sjis, "cp932")):
        try:
            s = data.decode(codec)
        except UnicodeDecodeError:
            continue
        if len(s) == 1 and ord(s) not in cps:
            cps.append(ord(s))
    return cps


def c_bytes(data, indent="    "):
    return indent + ", ".join("0x%02X" % b for b in data)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kanji", required=True, help="16x16 JIS X 0208 BDF (shnmk16.bdf)")
    ap.add_argument("--ascii", required=True, help="8x16 ISO8859-1 BDF (shnm8x16a.bdf)")
    ap.add_argument("--kana", required=True, help="8x16 JIS X 0201 BDF (shnm8x16r.bdf)")
    ap.add_argument("--out-dir", default=".", help="output directory")
    ap.add_argument("--name", default="shinonome16", help="base name of the output files")
    args = ap.parse_args()

    kanji = parse_bdf(args.kanji)
    ascii_ = parse_bdf(args.ascii)
    kana = parse_bdf(args.kana)

    # ---- full-width glyphs -------------------------------------------------
    full_glyphs = []          # LCD bitmaps, in JIS order
    key_to_index = {}         # Unicode -> glyph index
    geta_index = None
    for jis in sorted(kanji):
        cps = jis_to_unicode(jis)
        if not cps:
            print("warning: JIS 0x%04X has no Unicode mapping, skipped" % jis, file=sys.stderr)
            continue
        index = len(full_glyphs)
        full_glyphs.append(to_lcd_pages(*kanji[jis], cell_width=16))
        if jis == GETA_JIS:
            geta_index = index
        for cp in cps:
            if cp > 0xFFFF:
                continue
            # keep the first (EUC-JP) assignment if two JIS codes collide
            key_to_index.setdefault(cp, index)
    if geta_index is None:
        sys.exit("error: substitute glyph JIS 0x%04X not found" % GETA_JIS)
    keys = sorted(key_to_index)

    # ---- half-width glyphs -------------------------------------------------
    half_glyphs = []
    for code in range(ASCII_FIRST, ASCII_LAST + 1):
        half_glyphs.append(to_lcd_pages(*ascii_[code], cell_width=8))
    for code in range(KANA_FIRST, KANA_LAST + 1):
        half_glyphs.append(to_lcd_pages(*kana[code], cell_width=8))

    name = args.name
    upper = name.upper()
    src = os.path.basename(args.kanji) + ", " + os.path.basename(args.ascii) + \
        ", " + os.path.basename(args.kana)

    # ---- header ------------------------------------------------------------
    h_path = os.path.join(args.out_dir, name + "_data.h")
    with open(h_path, "w", newline="\n") as f:
        f.write("""\
// Generated by tools/bdf2c.py from Shinonome font ({src}). DO NOT EDIT.
// Shinonome font: Public Domain, The Electronic Font Open Laboratory
//   http://openlab.ring.gr.jp/efont/shinonome/
//
// Glyph layout (LCD page format, W = glyph width):
//   glyph[0 .. W-1]  : page 0 (rows 0-7),  one byte per column
//   glyph[W .. 2W-1] : page 1 (rows 8-15), one byte per column
//   bit n            : row (page * 8 + n), bit 0 = top

#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {{
#endif

#define {U}_HEIGHT        16
#define {U}_FULL_WIDTH    16
#define {U}_HALF_WIDTH    8
#define {U}_FULL_BYTES    32
#define {U}_HALF_BYTES    16

// Full-width glyphs, looked up by Unicode via {n}_full_key[] (sorted)
#define {U}_FULL_GLYPHS   {ng}
#define {U}_FULL_KEYS     {nk}
#define {U}_GETA_INDEX    {geta}   // '〓' substitute glyph
extern const uint16_t {n}_full_key[{U}_FULL_KEYS];
extern const uint16_t {n}_full_index[{U}_FULL_KEYS];
extern const uint8_t  {n}_full_glyph[{U}_FULL_GLYPHS][{U}_FULL_BYTES];

// Half-width glyphs: ASCII 0x{af:02X}-0x{al:02X}, then U+FF61-U+FF9F (JIS X 0201 kana)
#define {U}_ASCII_FIRST   0x{af:02X}
#define {U}_ASCII_LAST    0x{al:02X}
#define {U}_KANA_INDEX    {ki}
#define {U}_KANA_FIRST    0x{kuf:04X}
#define {U}_KANA_LAST     0x{kul:04X}
#define {U}_HALF_GLYPHS   {nh}
extern const uint8_t  {n}_half_glyph[{U}_HALF_GLYPHS][{U}_HALF_BYTES];

#ifdef __cplusplus
}}
#endif
""".format(src=src, U=upper, n=name, ng=len(full_glyphs), nk=len(keys), geta=geta_index,
           af=ASCII_FIRST, al=ASCII_LAST, ki=ASCII_LAST - ASCII_FIRST + 1,
           kuf=KANA_UNICODE_FIRST, kul=KANA_UNICODE_FIRST + KANA_LAST - KANA_FIRST,
           nh=len(half_glyphs)))

    # ---- data --------------------------------------------------------------
    c_path = os.path.join(args.out_dir, name + "_data.c")
    with open(c_path, "w", newline="\n") as f:
        f.write("// Generated by tools/bdf2c.py from Shinonome font (%s). DO NOT EDIT.\n" % src)
        f.write("// Shinonome font: Public Domain, The Electronic Font Open Laboratory\n\n")
        f.write('#include "%s_data.h"\n\n' % name)

        f.write("const uint16_t %s_full_key[%s_FULL_KEYS] = {\n" % (name, upper))
        for i in range(0, len(keys), 12):
            f.write("    " + ", ".join("0x%04X" % k for k in keys[i:i + 12]) + ",\n")
        f.write("};\n\n")

        f.write("const uint16_t %s_full_index[%s_FULL_KEYS] = {\n" % (name, upper))
        idx = [key_to_index[k] for k in keys]
        for i in range(0, len(idx), 12):
            f.write("    " + ", ".join("%4d" % v for v in idx[i:i + 12]) + ",\n")
        f.write("};\n\n")

        f.write("const uint8_t %s_full_glyph[%s_FULL_GLYPHS][%s_FULL_BYTES] = {\n"
                % (name, upper, upper))
        for i, g in enumerate(full_glyphs):
            f.write("    { // %d\n%s,\n%s },\n" % (
                i, c_bytes(g[:16], "      "), c_bytes(g[16:], "      ")))
        f.write("};\n\n")

        f.write("const uint8_t %s_half_glyph[%s_HALF_GLYPHS][%s_HALF_BYTES] = {\n"
                % (name, upper, upper))
        codes = list(range(ASCII_FIRST, ASCII_LAST + 1)) + \
            list(range(KANA_UNICODE_FIRST, KANA_UNICODE_FIRST + KANA_LAST - KANA_FIRST + 1))
        for cp, g in zip(codes, half_glyphs):
            f.write("    { %s }, // U+%04X\n" % (", ".join("0x%02X" % b for b in g), cp))
        f.write("};\n")

    print("full-width: %d glyphs, %d keys / half-width: %d glyphs" %
          (len(full_glyphs), len(keys), len(half_glyphs)))
    print("wrote %s, %s" % (h_path, c_path))


if __name__ == "__main__":
    main()
