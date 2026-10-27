#!/usr/bin/env sh
# Create/update the public demo on Hugging Face Spaces.
#
#   HF_TOKEN=hf_xxx ./scripts/deploy-hf-space.sh <hf-username> [space-name]
#
# The Space repo only holds deploy/huggingface/{Dockerfile,README.md}; the Space build clones
# this GitHub repository (main), so pushing to GitHub + "Factory rebuild" on the Space updates it.
# HF_TOKEN needs "write" access (huggingface.co/settings/tokens). Revoke it afterwards if you like.
set -e
USER_NAME="$1"
SPACE="${2:-docintel}"
[ -n "$USER_NAME" ] && [ -n "$HF_TOKEN" ] || { echo "usage: HF_TOKEN=... $0 <hf-username> [space-name]"; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Creating Space $USER_NAME/$SPACE (ok if it already exists)..."
curl -s -X POST https://huggingface.co/api/repos/create \
  -H "Authorization: Bearer $HF_TOKEN" -H "Content-Type: application/json" \
  -d "{\"type\":\"space\",\"name\":\"$SPACE\",\"sdk\":\"docker\",\"private\":false}" | head -c 300; echo

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git clone -q "https://$USER_NAME:$HF_TOKEN@huggingface.co/spaces/$USER_NAME/$SPACE" "$TMP/space"
REF="$(git -C "$ROOT" rev-parse origin/main)"  # deploy what is on GitHub, not local edits
sed "s/^ARG GIT_REF=.*/ARG GIT_REF=$REF/" "$ROOT/deploy/huggingface/Dockerfile" > "$TMP/space/Dockerfile"
echo "Pinning Space build to commit $REF"
cp "$ROOT/deploy/huggingface/README.md" "$TMP/space/README.md"
cd "$TMP/space"
git add Dockerfile README.md
if git diff --cached --quiet; then
  echo "Space files unchanged; trigger a rebuild from the Space settings to pick up new GitHub commits."
else
  git -c user.name="$USER_NAME" -c user.email="$USER_NAME@users.noreply.huggingface.co" \
    commit -q -m "Deploy DocIntel demo (builds from github.com/piyaldeb/ai-document-intelligence)"
  git push -q origin HEAD:main
fi
echo "Space: https://huggingface.co/spaces/$USER_NAME/$SPACE  (build takes ~10-15 min the first time)"
