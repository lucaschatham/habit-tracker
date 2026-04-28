#!/usr/bin/env bash
set -euo pipefail

# Default for progress photos: strip EXIF/GPS metadata before publishing.
# Requires ImageMagick's `magick` command.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

find "$ROOT_DIR/photos" "$ROOT_DIR/public/photos" \
  -type f \( -iname '*.jpg' -o -iname '*.jpeg' \) -print0 |
  while IFS= read -r -d '' file; do
    tmp="${file}.tmp.jpg"
    magick "$file" -strip "$tmp"
    mv "$tmp" "$file"
  done

