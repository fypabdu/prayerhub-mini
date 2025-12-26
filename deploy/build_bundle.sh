#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bundle_name="prayerhub-install-bundle.zip"
bundle_path="${root_dir}/${bundle_name}"

cd "$root_dir"

rm -f "$bundle_path"

python -m build --wheel --outdir dist

staging_dir="$(mktemp -d)"
trap 'rm -rf "$staging_dir"' EXIT

mkdir -p "$staging_dir/dist"
cp dist/*.whl "$staging_dir/dist/"
cp requirements.txt "$staging_dir/"
cp deploy/prayerhub.service "$staging_dir/"
cp deploy/install.sh "$staging_dir/"
cp config.example.yml "$staging_dir/"
cp README_INSTALL.md "$staging_dir/"

cd "$staging_dir"
find . -type f -print0 | sort -z | xargs -0 zip -X "$bundle_path" >/dev/null

echo "Created bundle: $bundle_path"
