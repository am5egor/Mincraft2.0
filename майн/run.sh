#!/usr/bin/env bash
# Запуск Кубозема на Linux. Параметры передаются в игру: ./run.sh --radius 6
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

# Отдельная папка: окружение .venv, созданное на Windows, здесь не работает.
VENV=".venv-linux"
MARKER="$VENV/.installed"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Не найден python3. Установите его, например: sudo apt install python3 python3-venv" >&2
    exit 1
fi

if [ ! -x "$VENV/bin/python" ]; then
    echo "Создаю окружение в $VENV..."
    if ! python3 -m venv "$VENV"; then
        echo "Не удалось создать окружение. Попробуйте: sudo apt install python3-venv" >&2
        exit 1
    fi
fi

if [ ! -f "$MARKER" ] || [ requirements.txt -nt "$MARKER" ]; then
    echo "Устанавливаю библиотеки..."
    "$VENV/bin/python" -m pip install --disable-pip-version-check -r requirements.txt
    touch "$MARKER"
fi

exec "$VENV/bin/python" main.py "$@"
