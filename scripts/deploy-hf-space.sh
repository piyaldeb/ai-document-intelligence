#!/usr/bin/env sh
# Create/update the public demo on Hugging Face Spaces.
#
#   HF_TOKEN=hf_xxx ./scripts/deploy-hf-space.sh [hf-username] [space-name]
#
# The username defaults to the owner of the token. The Space repo only holds
# deploy/huggingface/{Dockerfile,README.md}; the Space build clones this GitHub repository at
# the pinned commit. HF_TOKEN needs "write" access (huggingface.co/settings/tokens).
set -e
case "$HF_TOKEN" in
  hf_YOUR*|"") echo "Set HF_TOKEN to your real token (huggingface.co/settings/tokens, type: Write)."; exit 1 ;;
esac

WHOAMI="$(curl -s https://huggingface.co/api/whoami-v2 -H "Authorization: Bearer $HF_TOKEN")"
TOKEN_USER="$(printf '%s' "$WHOAMI" | sed -n 's/^{"type":"user","id":"[^"]*","name":"\([^"]*\)".*/\1/p')"
if [ -z "$TOKEN_USER" ]; then
  echo "Hugging Face rejected the token: $WHOAMI"
  exit 1
fi
USER_NAME="${1:-$TOKEN_USER}"
case "$USER_NAME" in YOUR_*) USER_NAME="$TOKEN_USER" ;; esac
SPACE="${2:-docintel}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "Token belongs to: $TOKEN_USER - deploying to $USER_NAME/$SPACE"

echo "Creating Space (ok if it already exists)..."
curl -s -X POST https://huggingface.co/api/repos/create \
  -H "Authorization: Bearer $HF_TOKEN" -H "Content-Type: application/json" \
  -d "{\"type\":\"space\",\"name\":\"$SPACE\",\"sdk\":\"docker\",\"private\":false}" | head -c 300; echo

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git clone -q "https://$USER_NAME:$HF_TOKEN@huggingface.co/spaces/$USER_NAME/$SPACE" "$TMP/space"
REF="$(git -C "$ROOT" rev-parse origin/main)"  # deploy what is on GitHub, not local edits
sed "s/^ARG GIT_REF=.*/ARG GIT_REF=$REF/" "$ROOT/deploy/huggingface/Dockerfile" > "$TMP/space/Dockerfile"
cp "$ROOT/deploy/huggingface/README.md" "$TMP/space/README.md"
echo "Pinning Space build to commit $REF"
cd "$TMP/space"
git add Dockerfile README.md
if git diff --cached --quiet; then
  echo "Space files unchanged; use 'Factory rebuild' in the Space settings to rebuild."
else
  git -c user.name="$USER_NAME" -c user.email="$USER_NAME@users.noreply.huggingface.co" \
    commit -q -m "Deploy DocIntel demo (builds from github.com/piyaldeb/ai-document-intelligence)"
  git push -q origin HEAD:main
fi
echo
echo "Done. Space: https://huggingface.co/spaces/$USER_NAME/$SPACE"
echo "First build takes ~10-15 minutes; watch the 'Logs' tab there. Direct app URL: https://$(echo "$USER_NAME-$SPACE" | tr 'A-Z_.' 'a-z--').hf.space"
