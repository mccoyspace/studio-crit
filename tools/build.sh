#!/usr/bin/env bash
# Rebuild corpus/ from sources/. Needs: python3 with beautifulsoup4 + Pillow, tesseract, poppler (pdftoppm).
# Intermediate files (page images, OCR) go to $WORK (default: .work/, safe to delete).
set -euo pipefail
cd "$(dirname "$0")/.."
WORK="${WORK:-.work}"
EPUB="sources/Draw It with Your Eyes Closed-The Art of the Art Assignment.epub"
PDF="sources/I like your work-art and etiquette.pdf"
mkdir -p "$WORK/epub" "$WORK/epub_img_ocr" "$WORK/pdf_ocr"

# --- Draw It with Your Eyes Closed (EPUB) -------------------------------------
unzip -o -q "$EPUB" -d "$WORK/epub"
# OCR the scanned images (512px) at 3x so text-bearing ones get a raw transcription
python3 -I -c '
import sys, pathlib
from PIL import Image
src, dst = map(pathlib.Path, sys.argv[1:3])
for f in src.glob("*.jpg"):
    im = Image.open(f).convert("L"); im = im.resize((im.width * 3, im.height * 3))
    im.save(dst / (f.stem + ".png"))
' "$WORK/epub/images" "$WORK/epub_img_ocr"
ls "$WORK"/epub_img_ocr/*.png | xargs -P 8 -I{} sh -c 'tesseract "$1" "${1%.png}" --psm 6 -l eng >/dev/null 2>&1' _ {}
python3 -I tools/parse_epub.py "$WORK/epub" "$WORK/epub_img_ocr" tools/data/epub_figures.json \
    tools/data/transcriptions corpus/draw-it-with-your-eyes-closed

# --- I Like Your Work (scanned PDF) --------------------------------------------
pdftoppm -r 300 -gray -png "$PDF" "$WORK/pdf_ocr/pg"
ls "$WORK"/pdf_ocr/pg-*.png | xargs -P 8 -I{} sh -c 'tesseract "$1" "${1%.png}" --psm 6 -l eng tsv >/dev/null 2>&1' _ {}
# the contributors page is two columns: OCR each half separately
python3 -I -c '
import sys
from PIL import Image
d = sys.argv[1]; im = Image.open(f"{d}/pg-58.png"); w, h = im.size
im.crop((0, 0, w // 2 + 10, h)).save(f"{d}/bios-L.png"); im.crop((w // 2 - 10, 0, w, h)).save(f"{d}/bios-R.png")
' "$WORK/pdf_ocr"
for f in bios-L bios-R; do tesseract "$WORK/pdf_ocr/$f.png" "$WORK/pdf_ocr/$f" --psm 6 -l eng tsv >/dev/null 2>&1; done
mkdir -p corpus/i-like-your-work/images
python3 -I tools/parse_pdf.py "$WORK/pdf_ocr" tools/data/pdf_corrections.json corpus/i-like-your-work "$WORK/pdf_ocr"

python3 -I tools/build_index.py corpus
# logical units: resolve the hand annotations in tools/data/units/ against the rebuilt text
python3 -I tools/build_units.py corpus tools/data/units
