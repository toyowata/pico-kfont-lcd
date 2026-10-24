/**
 * Copyright (c) 2020-2025 Raspberry Pi (Trading) Ltd.
 *
 * SPDX-License-Identifier: Apache-2.0
 */


#include <stdlib.h>
#include <cstring>

#include "pico/stdlib.h"
#include "hardware/spi.h"

#include "shinonome_font.h"

#define numOfCharBuffer 40
uint32_t uBuf[numOfCharBuffer];

#define LCD_CS_PIN 17
#define LCD_RS_PIN 20
#define LCD_WIDTH 128
#define LCD_HEIGHT 48
#define LCD_PAGES (LCD_HEIGHT / 8)

int pico_led_init(void) {
    gpio_init(PICO_DEFAULT_LED_PIN);
    gpio_set_dir(PICO_DEFAULT_LED_PIN, GPIO_OUT);
    gpio_pull_up(PICO_DEFAULT_LED_PIN);
    return PICO_OK;
}

static inline void cs_select(int cs_pin) {
    asm volatile("nop \n nop \n nop");
    gpio_put(cs_pin, 0);  // Active low
    asm volatile("nop \n nop \n nop");
}

static inline void cs_deselect(int cs_pin) {
    asm volatile("nop \n nop \n nop");
    gpio_put(cs_pin, 1);
    asm volatile("nop \n nop \n nop");
}

void wr_cmd(unsigned char cmd)
{
    gpio_put(LCD_RS_PIN, 0);
    cs_select(LCD_CS_PIN);
    sleep_us(2);
    spi_write_blocking(spi0, &cmd, 1);
    cs_deselect(LCD_CS_PIN);
}

void wr_dat(unsigned char dat)
{
    gpio_put(LCD_RS_PIN, 1);
    cs_select(LCD_CS_PIN);
    sleep_us(2);
    spi_write_blocking(spi0, &dat, 1);
    cs_deselect(LCD_CS_PIN);
}

// Set the column / page address and write len bytes of display data.
void wr_page(int x, int page, const uint8_t *data, size_t len)
{
    // Group commands to send them in a single SPI transaction for efficiency.
    uint8_t cmds[] = {
        (uint8_t)(0x00 + (x & 0x0f)),         // set column low nibble
        (uint8_t)(0x10 + ((x >> 4) & 0x0f)),  // set column hi nibble
        (uint8_t)(0xB0 + page)                // set page address
    };
    gpio_put(LCD_RS_PIN, 0);
    cs_select(LCD_CS_PIN);
    sleep_us(2);
    spi_write_blocking(spi0, cmds, sizeof(cmds));
    cs_deselect(LCD_CS_PIN);

    gpio_put(LCD_RS_PIN, 1);
    cs_select(LCD_CS_PIN);
    sleep_us(2);
    spi_write_blocking(spi0, data, len);
    cs_deselect(LCD_CS_PIN);
}

void clear_lcd(void) {
    // Use a static buffer to avoid stack allocation and memset on every call.
    // The buffer is initialized to zeros only once.
    static const uint8_t zeros[LCD_WIDTH] = {0};

    for (int i = 0; i < LCD_PAGES; i++) {
        wr_page(0, i, zeros, sizeof(zeros));
    }
}

// Draw a glyph at column x, page y (occupies pages y and y + 1).
// The bitmap is already in the LCD page format, so each page is sent
// directly from flash with no conversion.
// width: 16 for full-width (Kanji), 8 for half-width (ANK)
void draw_char(int x, int y, const uint8_t *bitmap, int width)
{
    if (width != 8 && width != 16)
        return;

    for (int page = 0; page < 2; page++) {
        wr_page(x, y + page, &bitmap[page * width], width);
    }
}

int pico_spi_init(void) {
    // This example will use SPI0 at 10MHz (ST7565R allows up to 20MHz).
    // LCD SPI setup
    spi_init(spi0, 10 * 1000 * 1000);
    spi_set_format(spi0, 8, SPI_CPOL_1, SPI_CPHA_1, SPI_MSB_FIRST);
    gpio_set_function(18, GPIO_FUNC_SPI);
    gpio_set_function(19, GPIO_FUNC_SPI);
    gpio_set_function(16, GPIO_FUNC_SPI);
    gpio_set_function(LCD_CS_PIN, GPIO_FUNC_SIO);

    // Chip select is active-low, so we'll initialise it to a driven-high state
    gpio_init(LCD_CS_PIN);
    gpio_set_dir(LCD_CS_PIN, GPIO_OUT);
    gpio_put(LCD_CS_PIN, 1);

    // LCD RS pin
    gpio_init(LCD_RS_PIN);
    gpio_set_dir(LCD_RS_PIN, GPIO_OUT);
    gpio_put(LCD_RS_PIN, 0);

    wr_cmd(0xAE);   // display off
    wr_cmd(0xA0);
    wr_cmd(0xC8);   // colum normal
    wr_cmd(0xA3);   // bias voltage
    wr_cmd(0x2c);
    sleep_ms(2);
    wr_cmd(0x2e);
    sleep_ms(2);
    wr_cmd(0x2F);   // power on
    wr_cmd(0x23);
    wr_cmd(0x81);   // electronic volume (contrast)
    wr_cmd(0x1a);   // 0x00-0x3F
    wr_cmd(0xA4);   // LCD display ram
    wr_cmd(0x40);   // start line = 0
    wr_cmd(0xa6);
    wr_cmd(0xAF);   // display ON

    clear_lcd();

    return PICO_OK;
}

void pico_set_led(bool led_on) {
    gpio_put(PICO_DEFAULT_LED_PIN, led_on);
}

// Convert UTF-8 string to Unicode code points.
// cpBuffer must have room for maxLen elements, including the 0 terminator.
// Returns the number of converted characters (excluding the terminator).
int conv_utf8(const char* utfBuffer, uint32_t* cpBuffer, int maxLen)
{
    const uint8_t *s = (const uint8_t *)utfBuffer;
    int ret = 0;

    if (maxLen <= 0)
        return 0;

    while (*s != 0 && ret < maxLen - 1) {
        uint32_t cp;
        int len;

        if (s[0] < 0x80) {
            cp = s[0];
            len = 1;
        } else if (s[0] >= 0xC2 && s[0] <= 0xDF) {
            cp = s[0] & 0x1F;
            len = 2;
        } else if ((s[0] & 0xF0) == 0xE0) {
            cp = s[0] & 0x0F;
            len = 3;
        } else if (s[0] >= 0xF0 && s[0] <= 0xF4) {
            cp = s[0] & 0x07;
            len = 4;
        } else {
            // invalid lead byte
            s++;
            continue;
        }

        // extract valid bits of continuation bytes (also stops at the terminator)
        int i;
        for (i = 1; i < len; i++) {
            if ((s[i] & 0xC0) != 0x80)
                break;
            cp = (cp << 6) | (s[i] & 0x3F);
        }
        s += i;
        if (i < len) {
            // truncated or invalid sequence
            continue;
        }
        if (cp < 0x20) {
            // control characters
            continue;
        }

        cpBuffer[ret++] = cp;
    }
    cpBuffer[ret] = 0;

    return ret;
}

void draw_utf8(int offset_x, int offset_y, const char *buf_u)
{
    if (offset_x < 0 || offset_y < 0)
        return;

    int len = conv_utf8(buf_u, uBuf, numOfCharBuffer);
    int xpos = offset_x;
    int ypos = offset_y;

    for(int i = 0; i < len; i++) {
        const uint8_t *bitmap;
        int width = shinonome_get_glyph(uBuf[i], &bitmap);
        if (xpos + width > LCD_WIDTH) {
            // wrap to the next line
            xpos = 0;
            ypos += 2;
        }
        if (ypos + 2 > LCD_PAGES)
            break;
        draw_char(xpos, ypos, bitmap, width);
        xpos += width;
    }
}

int main() {
    bool blink = true;

    //stdio_init_all();
    pico_led_init();
    pico_spi_init();

    draw_utf8(0, 2, "第二水準: 薔薇");
    draw_utf8(0, 0, "日本語表示ｱｲｳｴｵ");
    draw_utf8(0, 4, "Picoで漢字表示§");

    while (1) {
        pico_set_led(blink);
        blink = !blink;
        sleep_ms(500);
    }

    return 0;
}
