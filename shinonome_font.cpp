/**
 * Copyright (c) 2026 Toyomasa Watarai
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include "shinonome_font.h"

// Binary search the sorted Unicode key table
static int find_full_glyph(uint16_t key)
{
    int lo = 0;
    int hi = SHINONOME16_FULL_KEYS - 1;

    while (lo <= hi) {
        int mid = (lo + hi) / 2;
        uint16_t k = shinonome16_full_key[mid];
        if (k == key)
            return shinonome16_full_index[mid];
        if (k < key)
            lo = mid + 1;
        else
            hi = mid - 1;
    }
    return -1;
}

int shinonome_get_glyph(uint32_t cp, const uint8_t **bitmap)
{
    if (cp >= SHINONOME16_ASCII_FIRST && cp <= SHINONOME16_ASCII_LAST) {
        // ASCII
        *bitmap = shinonome16_half_glyph[cp - SHINONOME16_ASCII_FIRST];
        return SHINONOME16_HALF_WIDTH;
    }
    if (cp >= SHINONOME16_KANA_FIRST && cp <= SHINONOME16_KANA_LAST) {
        // Half-width Katakana
        *bitmap = shinonome16_half_glyph[SHINONOME16_KANA_INDEX + (cp - SHINONOME16_KANA_FIRST)];
        return SHINONOME16_HALF_WIDTH;
    }

    int index = (cp <= 0xFFFF) ? find_full_glyph((uint16_t)cp) : -1;
    if (index < 0)
        index = SHINONOME16_GETA_INDEX;     // substitute for unsupported characters
    *bitmap = shinonome16_full_glyph[index];
    return SHINONOME16_FULL_WIDTH;
}
