# Devcontainer Start: Sync `lib-examples` from `pydantic-schemaforms`

## Goal
When the devcontainer starts, clear `lib-examples/` and repopulate it from the installed `pydantic_schemaforms` package examples.

## Why this approach
- `lib-examples/` is disposable for your workflow.
- Re-syncing on start guarantees fresh example content.
- No manual copy steps after container rebuild/start.

## Implementation plan
1. Add a shell script at `scripts/sync-lib-examples.sh`.
2. Script behavior:
   - Resolve package install location with Python.
   - Find bundled examples folder in the installed package.
   - Remove current `lib-examples/*` contents.
   - Copy package examples into `lib-examples/`.
3. Hook script in `.devcontainer/devcontainer.json` using `postStartCommand`.
4. Keep existing `postCreateCommand` for venv + dependencies.

## Draft script logic
```bash
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PY_BIN=".venv/bin/python3"
if [[ ! -x "$PY_BIN" ]]; then
  PY_BIN="python3"
fi

PKG_ROOT="$($PY_BIN - <<'PY'
import pathlib
import pydantic_schemaforms as m
print(pathlib.Path(m.__file__).resolve().parent)
PY
)"

SOURCE=""
for CANDIDATE in \
  "$PKG_ROOT/examples" \
  "$(dirname "$PKG_ROOT")/examples" \
  "$PKG_ROOT/lib-examples"; do
  if [[ -d "$CANDIDATE" ]]; then
    SOURCE="$CANDIDATE"
    break
  fi
done

if [[ -z "$SOURCE" ]]; then
  echo "Could not find package examples directory"
  exit 1
fi

rm -rf lib-examples/*
cp -R "$SOURCE"/. lib-examples/
echo "Synced lib-examples from: $SOURCE"
```

## Devcontainer hook (to add)
In `.devcontainer/devcontainer.json`:

```json
"postStartCommand": "bash scripts/sync-lib-examples.sh"
```

## Notes
- This intentionally overwrites local files in `lib-examples/` on each container start.
- If you want sync only on rebuild/create (not every start), use `postCreateCommand` instead.
