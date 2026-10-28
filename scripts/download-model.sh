#!/usr/bin/env bash
# Скачивает маленькую русскую модель Vosk (~45 МБ) в ~/.local/share/namewatch
set -euo pipefail
DIR="${XDG_DATA_HOME:-$HOME/.local/share}/namewatch"
NAME="vosk-model-small-ru-0.22"
mkdir -p "$DIR"
cd "$DIR"
[ -d "$NAME" ] && { echo "Уже есть: $DIR/$NAME"; exit 0; }
curl -fL -o "$NAME.zip" "https://alphacephei.com/vosk/models/$NAME.zip"
unzip -q "$NAME.zip" && rm "$NAME.zip"
echo "Готово: $DIR/$NAME"
