#!/usr/bin/env bash
# Read-only discovery for the auth.codestra.co 502 repair on Server A.
set -Eeuo pipefail

AUTH_HOST="auth.codestra.co"
CANONICAL_REALM="codestra"
CANONICAL_RUNTIME_IP="49.12.145.107"
DISCOVERY_PATH="/realms/${CANONICAL_REALM}/.well-known/openid-configuration"

printf 'SERVER\n'
hostname
hostname -I 2>/dev/null || true

printf '\nDNS\n'
getent ahostsv4 "$AUTH_HOST" 2>/dev/null | awk '{print $1}' | sort -u || true

printf '\nPUBLIC_AUTH_STATUS\n'
curl -sS --connect-timeout 5 --max-time 10 \
  -o /dev/null \
  -w 'URL=%{url_effective} HTTP=%{http_code} REMOTE_IP=%{remote_ip} TLS_VERIFY=%{ssl_verify_result}\n' \
  "https://${AUTH_HOST}${DISCOVERY_PATH}" || true

printf '\nCANONICAL_RUNTIME_DIRECT_STATUS\n'
# Force only this diagnostic request to the recorded canonical runtime IP while
# preserving the auth.codestra.co Host/SNI identity. This does not change DNS.
curl -sS --connect-timeout 5 --max-time 10 \
  --resolve "${AUTH_HOST}:443:${CANONICAL_RUNTIME_IP}" \
  -o /dev/null \
  -w 'FORCED_IP=%{remote_ip} HTTP=%{http_code} TLS_VERIFY=%{ssl_verify_result}\n' \
  "https://${AUTH_HOST}${DISCOVERY_PATH}" || true

printf '\nLISTENERS_80_443\n'
ss -lntp 2>/dev/null | awk 'NR == 1 || $4 ~ /:80$|:443$/' || true

printf '\nCADDY_PROCESSES_AND_CONTAINERS\n'
ps -eo pid,user,cmd | grep -E '[c]addy' || true
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' \
    | awk 'NR == 1 || tolower($0) ~ /caddy|keycloak/'

  printf '\nCADDY_MOUNTS\n'
  while IFS= read -r container; do
    [[ -n "$container" ]] || continue
    printf 'CONTAINER=%s\n' "$container"
    docker inspect "$container" --format \
      '{{range .Mounts}}{{printf "%s -> %s RW=%t\n" .Source .Destination .RW}}{{end}}'
  done < <(docker ps --format '{{.Names}}' | grep -i caddy || true)
else
  printf 'DOCKER=UNAVAILABLE_OR_UNAUTHORIZED\n'
fi

printf '\nCADDY_CONFIG_CANDIDATES\n'
for root in /etc/caddy /opt/codestra /srv/codestra-middleware; do
  [[ -d "$root" ]] || continue
  find "$root" -maxdepth 5 -type f \
    \( -name 'Caddyfile' -o -name '*.caddy' -o -name '*.Caddyfile' \) \
    -print 2>/dev/null || true
done | sort -u

printf '\nAUTH_ROUTE_REFERENCES\n'
# Print only matching routing lines and nearby reverse_proxy lines; do not dump
# complete environment files or secret stores.
for root in /etc/caddy /opt/codestra /srv/codestra-middleware; do
  [[ -d "$root" ]] || continue
  grep -R -n -E \
    'auth\.codestra\.co|reverse_proxy[[:space:]].*keycloak|49\.12\.145\.107' \
    "$root" \
    --include='Caddyfile' --include='*.caddy' --include='*.Caddyfile' \
    2>/dev/null || true
done | head -n 200

printf '\nLOCAL_KEYCLOAK_ENDPOINTS\n'
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}' | grep -i keycloak || true
fi
ss -lntp 2>/dev/null | grep -E ':8080\b|:18082\b' || true

printf '\nRESULT\n'
printf 'DISCOVERY_MODE=READ_ONLY\n'
printf 'LIVE_CONFIGURATION_CHANGED=NO\n'
printf 'BOOKED4SEASONS_CHANGED=NO\n'
printf 'NEXT_GATE=IDENTIFY_EXACT_CADDY_UPSTREAM_THEN_VALIDATE_CANDIDATE\n'
