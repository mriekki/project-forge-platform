#!/usr/bin/env bash
# Credential-free regression for the exact npm CLI used by one-use successor
# release. Never invokes npm publish, installs package scripts or uses OIDC.
set -euo pipefail
umask 077
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
mkdir "$scratch/publisher"
curl --fail --silent --show-error --max-time 60 --retry 2 --proto '=https' \
  https://registry.npmjs.org/npm/-/npm-11.21.0.tgz > "$scratch/npm-11.21.0.tgz"
node -e '
 const fs=require("node:fs"),crypto=require("node:crypto");
 const actual="sha512-"+crypto.createHash("sha512").update(fs.readFileSync(process.argv[1])).digest("base64");
 const expected="sha512-Zov8KhamNneiLdELtj5YALtNmJW4L4fCLTzjfpzXG2w6MSHcf0UxgdlK5uloCuksWT+7mGUU7wi79cO6RqivPg==";
 if(actual!==expected)process.exit(2);
' "$scratch/npm-11.21.0.tgz"
tar -xzf "$scratch/npm-11.21.0.tgz" -C "$scratch/publisher" --no-same-owner --no-same-permissions
cli="$scratch/publisher/package/bin/npm-cli.js"
# Explicitly deny token-bearing environment before either nonpublishing probe.
unset NODE_AUTH_TOKEN NPM_TOKEN NPM_CONFIG_USERCONFIG npm_config_userconfig NPM_CONFIG_GLOBALCONFIG npm_config_globalconfig GH_TOKEN
if npm_config_userconfig=/dev/null npm_config_globalconfig=/dev/null \
  node "$cli" --version > "$scratch/alias.out" 2>&1; then
  echo 'FAIL pinned npm 11 CLI unexpectedly accepted aliased config scopes' >&2
  exit 2
fi
if ! grep -Fq 'double-loading config' "$scratch/alias.out"; then
  echo 'FAIL aliased config did not fail at npm config collision' >&2
  exit 2
fi
user_config="$scratch/user.npmrc"
global_config="$scratch/global.npmrc"
: > "$user_config"
: > "$global_config"
test "$user_config" != "$global_config"
result="$(npm_config_userconfig="$user_config" npm_config_globalconfig="$global_config" \
  node "$cli" --version)"
test "$result" = 11.21.0
npm_config_userconfig="$user_config" npm_config_globalconfig="$global_config" \
  node "$cli" config list --json > "$scratch/config.out"
node -e '
 const fs=require("node:fs"),c=JSON.parse(fs.readFileSync(process.argv[1],"utf8"));
 if(!c||typeof c!=="object")process.exit(2);
' "$scratch/config.out"
echo 'PASS pinned npm 11.21.0 rejects aliased configs and accepts distinct private scopes (no publish)'
