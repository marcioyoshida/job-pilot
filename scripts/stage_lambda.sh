#!/usr/bin/env bash
# Hand-stage build/lambda for CDK (Onça pattern). No Docker.
# Installs a manylinux / CPython 3.11 PyYAML wheel so the host's 3.14
# interpreter cannot leak incompatible native extensions into the asset.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/build/lambda"

rm -rf "$DEST"
mkdir -p "$DEST/src"
rsync -a --delete \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  "$ROOT/src/" "$DEST/src/"

python3 -m pip install \
  --disable-pip-version-check \
  --quiet \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.11 \
  --only-binary=:all: \
  --upgrade \
  -t "$DEST" \
  'PyYAML>=6.0'

# pip --target drops caches + metadata we don't want in the zip
find "$DEST" -type d \( -name '__pycache__' -o -name '*.dist-info' -o -name '*.egg-info' \) -prune -exec rm -rf {} +
rm -rf "$DEST/bin"

test -f "$DEST/src/aws/handler.py"
test -d "$DEST/yaml"

echo "staged $DEST"
du -sh "$DEST"
