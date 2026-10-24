/**
 * Copyright (c) 2026 Toyomasa Watarai
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#pragma once

#include <stdint.h>

#include "shinonome16_data.h"

/** Look up a Shinonome 16-dot glyph by Unicode code point
 *
 *  The returned bitmap is already in the LCD page format
 *  (bitmap[0..width-1]: upper 8 rows, bitmap[width..2*width-1]: lower 8 rows,
 *  bit 0 = top), so it can be sent to the LCD as is.
 *  Full-width characters not in the font are replaced with '〓'.
 *
 *  @param cp Unicode code point
 *  @param bitmap receives a pointer to the glyph bitmap in flash
 *  @return font width (8 or 16)
 */
int shinonome_get_glyph(uint32_t cp, const uint8_t **bitmap);
