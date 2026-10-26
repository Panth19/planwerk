#!/usr/bin/env bash
# Cut a release: scripts/release.sh 1.0.0
# Clean main, full suite green, version bumped in one place each, annotated tag.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="${1:?usage: scripts/release.sh <version>}"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "version must look like 1.2.3" >&2; exit 1; }
[[ "$(git branch --show-current)" == "main" ]] || { echo "release from main only" >&2; exit 1; }
[[ -z "$(git status --porcelain -- . ':!CHANGELOG.md')" ]] || { echo "working tree not clean" >&2; exit 1; }
git rev-parse "v$VERSION" >/dev/null 2>&1 && { echo "v$VERSION already exists" >&2; exit 1; }
grep -q "## $VERSION" CHANGELOG.md || { echo "add a '## $VERSION' entry to CHANGELOG.md first" >&2; exit 1; }

echo "== full test suite"
PLANWERK_AUDIT_FILE=0 python3 -m pytest -q

echo "== bump to $VERSION"
sed -i.bak -E "s/^version = \".*\"/version = \"$VERSION\"/" pyproject.toml
sed -i.bak -E "s/^__version__ = \".*\"/__version__ = \"$VERSION\"/" planwerk/__init__.py
sed -i.bak -E "s/version=\"[0-9.]+\"/version=\"$VERSION\"/" planwerk/mcp_server.py
rm -f pyproject.toml.bak planwerk/__init__.py.bak planwerk/mcp_server.py.bak

git add pyproject.toml planwerk/__init__.py planwerk/mcp_server.py CHANGELOG.md
git commit -m "release: v$VERSION"
git tag -a "v$VERSION" -m "Planwerk $VERSION"
echo "tagged v$VERSION. Push with: git push --follow-tags"
