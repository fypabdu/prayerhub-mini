#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bundle_name="prayerhub-install-bundle.zip"
bundle_path="${root_dir}/${bundle_name}"

cd "$root_dir"

rm -f "$bundle_path"

if ! command -v poetry >/dev/null 2>&1; then
  echo "Poetry is required to build the bundle." >&2
  exit 1
fi

rm -rf dist
poetry build --format wheel

staging_dir="$(mktemp -d)"
trap 'rm -rf "$staging_dir"' EXIT

mkdir -p "$staging_dir/dist"
cp dist/*.whl "$staging_dir/dist/"
poetry export -f requirements.txt --without-hashes --output "$staging_dir/requirements.txt"
mkdir -p "$staging_dir/deploy"
cp deploy/prayerhub.service "$staging_dir/deploy/"
cp deploy/install.sh "$staging_dir/deploy/"
cp config.example.yml "$staging_dir/"
cp README_INSTALL.md "$staging_dir/"
if [ -d data/audio ]; then
  mkdir -p "$staging_dir/data"
  cp -R data/audio "$staging_dir/data/"
fi

cd "$staging_dir"
find . -type f -print0 | sort -z | xargs -0 zip -X "$bundle_path" >/dev/null

echo "Created bundle: $bundle_path"
