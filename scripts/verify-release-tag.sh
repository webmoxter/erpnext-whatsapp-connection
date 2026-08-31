#!/usr/bin/env bash
set -euo pipefail

tag="${1:?Usage: verify-release-tag.sh <tag>}"
root="$(git rev-parse --show-toplevel)"
signers="$root/release/trusted-release-signers"
[[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]
[[ -f "$signers" ]]
[[ "$(git cat-file -t "refs/tags/$tag")" == "tag" ]]
git -c gpg.format=ssh -c gpg.ssh.allowedSignersFile="$signers" verify-tag "$tag" >/dev/null
printf 'SIGNED_ADDON_TAG=%s\nSIGNED_ADDON_COMMIT=%s\n' "$tag" "$(git rev-list -n 1 "$tag")"
