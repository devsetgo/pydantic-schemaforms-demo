#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

REPO="devsetgo/pydantic-schemaforms"
BRANCH="main"

echo "Syncing lib-examples from github.com/${REPO} @ ${BRANCH}"

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

curl -fsSL "https://github.com/${REPO}/archive/refs/heads/${BRANCH}.tar.gz" \
  | tar -xz -C "$TMPDIR" --strip-components=2 \
    "${REPO##*/}-${BRANCH}/examples"

rm -rf lib-examples/*
cp -R "$TMPDIR"/. lib-examples/
echo "Done — lib-examples synced from ${REPO}@${BRANCH}"
