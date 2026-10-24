# pico-kfont-lcd

フリーの漢字フォント「東雲（しののめ）ゴシック 16ドット」を使って、日本語をAQM1248A LCDに表示します。  
[pico-kanji-lcd](https://github.com/toyowata/pico-kanji-lcd) をベースに、漢字フォントROM（GT20L16J1Y）を使わずにフォントデータをプログラムに内蔵しています。

# 使用した機材

* RP2040マイコンボードキット
https://akizukidenshi.com/catalog/g/g117542/
* AQM1248A小型グラフィック液晶ボード  
https://www.switch-science.com/products/11022

# デバイスとの接続

Raspberry Pi PicoとLCDは以下のように接続してください。

|Raspberry Pi Pico|AQM1248A|
|---|---|
|GPIO17|CS (3)|
|GPIO20|RS (2)|
|GPIO18|SCK (6)|
|GPIO19|SDI (4)|

# フォント

## 東雲フォント

[東雲フォント](http://openlab.ring.gr.jp/efont/shinonome/)（The Electronic Font Open Laboratory）はパブリックドメインのビットマップフォントです。以下の16ドットのBDFファイルを使っています。

|ファイル|内容|
|---|---|
|shnmk16.bdf|全角 16x16（JIS X 0208 の全6879文字）|
|shnm8x16a.bdf|半角 8x16（ASCII）|
|shnm8x16r.bdf|半角 8x16（JIS X 0201 半角カタカナ）|

## 変換済みデータ

変換済みのC言語の配列は `shinonome16_data.c` / `shinonome16_data.h` としてリポジトリに含まれているので、そのままビルドできます。

各グリフはLCD（ST7565R）の表示RAMと同じ並び（ページ形式）に変換されています。BDFは横方向（1バイト = 横8ドット）に並んでいますが、LCDは1バイトで縦8ドット（bit0が上）を描画するので、変換時に縦横を入れ替えています。このため、表示時にビット操作をする必要がなく、Flash上のデータをそのまま `spi_write_blocking()` でLCDに送れます。

```
幅Wのグリフ（全角 W=16 / 半角 W=8）
  glyph[0 .. W-1]  : 上半分（0〜7行目）、1列1バイト
  glyph[W .. 2W-1] : 下半分（8〜15行目）、1列1バイト
  bit n            : (ページ * 8 + n) 行目、bit0が上
```

全角文字はUnicodeのソート済みテーブルを二分探索して検索し、半角文字（ASCII、半角カタカナ）はインデックスで直接参照します。フォントにない全角文字は「〓」で表示します。

## フォントデータの再生成

変換スクリプト `tools/bdf2c.py` でフォントデータを生成します。

```bash
$ mkdir -p fonts && cd fonts
$ curl -LO http://openlab.ring.gr.jp/efont/dist/shinonome/shinonome-0.9.11p1.tar.bz2
$ tar xjf shinonome-0.9.11p1.tar.bz2
$ cd ..
$ python3 tools/bdf2c.py \
    --kanji fonts/shinonome-0.9.11/bdf/shnmk16.bdf \
    --ascii fonts/shinonome-0.9.11/bdf/shnm8x16a.bdf \
    --kana  fonts/shinonome-0.9.11/bdf/shnm8x16r.bdf \
    --out-dir .
```

# 必要なツールのインストール

## ツールチェインのインストール
以下の情報を参照して、ビルドに使用するツールチェインをインストールしてください。
https://pip-assets.raspberrypi.com/categories/610-raspberry-pi-pico/documents/RP-008276-DS-1-getting-started-with-pico.pdf

## pico-sdk
以下のサイトを参考にしてください。  
https://github.com/raspberrypi/pico-sdk

## picotool
以下のサイトを参考にしてください。  
https://github.com/raspberrypi/picotool

# プログラムのビルドと書き込み

## コマンドライン（cmake）でビルドする

```bash
$ mkdir build && cd build
```

### ビルド

PICO_SDK_PATHにPICO SDKをインストールしたパスを設定します。

```
$ export PICO_SDK_PATH=<pico-sdk-path>
```

ボード名を指定して、ビルドします。  
Raspberry Pi Pico の場合
```bash
$ cmake .. -GNinja -DPICO_BOARD=pico
$ ninja
```

Raspberry Pi Pico 2 の場合
```bash
$ cmake .. -GNinja -DPICO_BOARD=pico2
$ ninja
```

## Raspberry Pi Pico に書き込む
BOOTSELモードに設定し（基板上のボタンを押したまま電源を入れる）、以下のコマンドを実行します。

```bash
$ picotool load -x ./pico-kfont-lcd.uf2
```

## プログラムの実行

プログラム書き込み後、自動的にリセットされプログラムが起動します。  
