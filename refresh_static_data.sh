#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

python3 generate_static_data.py

if git diff --quiet -- data; then
  echo "No standings data changes to commit."
  exit 0
fi

git config user.name "QBK Standings Refresh"
git config user.email "joshschwartztv@gmail.com"
git remote set-url origin "https://${GITHUB_PERSONAL_ACCESS_TOKEN}@github.com/shwaz499/qbk-league-standings-embed.git"
git add data
git commit -m "Refresh standings data"
git push origin main
