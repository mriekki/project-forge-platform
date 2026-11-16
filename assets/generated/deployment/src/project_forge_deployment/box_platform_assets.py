"""Static shared-box platform assets and contract constants."""

PLATFORM_SCHEMA_VERSION = 1
PLATFORM_VERSION = "2"
PLATFORM_DISTRIBUTION = "trusted-lan-ubuntu-compose"
PLATFORM_ROOT = "/srv/project-forge-platform"
NETWORK_NAME = "caddy-net"
CADDY_CONTAINER = "project-forge-caddy"
CADDY_IMAGE = "caddy:2.8.4-alpine@sha256:af32e97399febea808609119bb21544d0265c58a02836576e32a2d082c262c17"
HOST_PLATFORM_WRITE_PHRASE = "[HOST PLATFORM WRITE]"

COMPOSE_YAML = f"""services:
  caddy:
    image: {CADDY_IMAGE}
    container_name: {CADDY_CONTAINER}
    restart: unless-stopped
    ports:
      - \"80:80\"
    volumes:
      - {PLATFORM_ROOT}/proxy/Caddyfile:/etc/caddy/Caddyfile:ro
      - {PLATFORM_ROOT}/proxy/conf.d:/etc/caddy/conf.d:ro
      - {PLATFORM_ROOT}/proxy/data:/data
      - {PLATFORM_ROOT}/proxy/config:/config
    networks:
      - {NETWORK_NAME}
    logging:
      driver: json-file
      options:
        max-size: \"10m\"
        max-file: \"3\"

networks:
  {NETWORK_NAME}:
    external: true
"""

CADDYFILE = """{
    auto_https off
}

import /etc/caddy/conf.d/*.caddy
"""

PUBLISH_ALIAS_SH = """#!/usr/bin/env bash
set -Eeuo pipefail

: \"${ALIAS_HOSTNAME:?ALIAS_HOSTNAME is required}\"

current_ip() {
    local ip
    ip=\"$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i==\"src\") print $(i+1)}')\"
    if [[ -z \"$ip\" ]]; then
        ip=\"$(ip -4 addr show scope global | grep -v 'docker' | grep -v 'br-' | awk '/inet / {print $2}' | cut -d/ -f1 | head -n1)\"
    fi
    printf '%s\\n' \"$ip\"
}

CURRENT_IP=\"$(current_ip)\"
if [[ -z \"$CURRENT_IP\" ]]; then
    echo \"project-forge alias publisher: could not determine host LAN IPv4 address.\" >&2
    exit 1
fi

/usr/bin/avahi-publish -a -R \"$ALIAS_HOSTNAME\" \"$CURRENT_IP\" &
AVAHI_PID=$!

cleanup() {
    kill \"$AVAHI_PID\" 2>/dev/null || true
    wait \"$AVAHI_PID\" 2>/dev/null || true
}
trap cleanup SIGTERM SIGINT EXIT

while kill -0 \"$AVAHI_PID\" 2>/dev/null; do
    sleep 10
    NEW_IP=\"$(current_ip)\"
    if [[ -n \"$NEW_IP\" && \"$NEW_IP\" != \"$CURRENT_IP\" ]]; then
        cleanup
        exit 0
    fi
done
wait \"$AVAHI_PID\"
"""

AVAHI_SERVICE = """[Unit]
Description=Project Forge mDNS alias %i
After=network-online.target avahi-daemon.service
Wants=network-online.target
Requires=avahi-daemon.service

[Service]
Type=simple
EnvironmentFile=/etc/project-forge-platform/aliases/%i.env
ExecStart=/usr/local/lib/project-forge-platform/publish-alias.sh
Restart=always
RestartSec=2
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
"""
