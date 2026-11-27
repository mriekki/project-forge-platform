#!/usr/bin/env bash
# Byte-exact public mirror qualification for the new independently qualified source 4.36.5 archive.
# This is read-only, uses only the current checkout and never publishes.
set -euo pipefail
expected="14a380dcca20a88e1272ac305d56f1ff902d4975083322a9bf970a50a5e434fd"
test "$(npm --version)" = '10.9.9'
node -e 'const p=require("./package.json");const c=require("./assets/components.json");const a=require("./assets/generated/ASSEMBLY.json");const l=require("./package-lock.json");for(const x of [p,c,a,l])if(x.version!=="4.36.5")process.exit(2);if(l.packages[""].version!=="4.36.5")process.exit(2)'
umask 077
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
user_config="$scratch/user.npmrc"
global_config="$scratch/global.npmrc"
: > "$user_config"
: > "$global_config"
test "$user_config" != "$global_config"
npm pack --ignore-scripts --offline --userconfig "$user_config" --globalconfig "$global_config" \
  --json --pack-destination "$scratch" > "$scratch/pack.json"
node -e 'const fs=require("node:fs");const p=JSON.parse(fs.readFileSync(process.argv[1],"utf8"));if(!Array.isArray(p)||p.length!==1||p[0].name!=="@mriekki/project-forge"||p[0].version!=="4.36.5"||p[0].filename!=="mriekki-project-forge-4.36.5.tgz")process.exit(2)' "$scratch/pack.json"
printf '%s  %s\n' "$expected" "$scratch/mriekki-project-forge-4.36.5.tgz" | sha256sum -c - > /dev/null
echo "PASS public 4.36.5 mirror matches independently Source-qualified archive sha256 $expected (NO PUBLISH)"
