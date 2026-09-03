#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

fail() {
  printf 'SERVER_COMMAND_INSTALL=FAIL\n' >&2
  exit 1
}

[[ "$(id -u)" -eq 0 ]] || fail
[[ $# -eq 2 ]] || fail

repository_dir="$1"
expected_sha="$2"
deploy_user="middleware-deploy"

[[ "$repository_dir" == /srv/codestra-middleware/* && "$repository_dir" != *".."* ]] || fail
[[ "$expected_sha" =~ ^[0-9a-f]{40}$ ]] || fail
id "$deploy_user" >/dev/null 2>&1 || fail
[[ -d "$repository_dir/.git" ]] || fail
[[ "$(git -C "$repository_dir" rev-parse HEAD)" == "$expected_sha" ]] || fail
[[ -z "$(git -C "$repository_dir" status --porcelain)" ]] || fail

source_dir="$repository_dir/deploy/production/server"
deploy_source="$source_dir/codestra-middleware-deploy"
backup_source="$source_dir/codestra-middleware-backup"
config_source="$source_dir/deploy.conf.example"

[[ -x "$deploy_source" && -x "$backup_source" && -f "$config_source" ]] || fail
bash -n "$deploy_source"
bash -n "$backup_source"

install -d -m 0700 -o root -g root /etc/codestra-middleware
install -d -m 0700 -o root -g root /var/lib/codestra-middleware/deployments
install -d -m 0700 -o root -g root /var/backups/codestra-middleware
install -d -m 0750 -o "$deploy_user" -g "$deploy_user" /srv/codestra-middleware/releases

install -m 0750 -o root -g root \
  "$deploy_source" \
  /usr/local/sbin/codestra-middleware-deploy
install -m 0750 -o root -g root \
  "$backup_source" \
  /usr/local/sbin/codestra-middleware-backup
install -m 0600 -o root -g root \
  "$config_source" \
  /etc/codestra-middleware/deploy.conf.example

if [[ ! -e /etc/codestra-middleware/deploy.conf ]]; then
  install -m 0600 -o root -g root \
    "$config_source" \
    /etc/codestra-middleware/deploy.conf
fi

sudoers_file=/etc/sudoers.d/codestra-middleware-deploy
temporary_sudoers="$(mktemp /etc/sudoers.d/.codestra-middleware-deploy.XXXXXX)"
trap 'rm -f "$temporary_sudoers"' EXIT
printf '%s ALL=(root) NOPASSWD: /usr/local/sbin/codestra-middleware-deploy\n' \
  "$deploy_user" >"$temporary_sudoers"
chmod 0440 "$temporary_sudoers"
visudo -cf "$temporary_sudoers" >/dev/null
mv -f "$temporary_sudoers" "$sudoers_file"
trap - EXIT
visudo -cf /etc/sudoers >/dev/null

printf 'SERVER_COMMAND_INSTALL=PASS\n'
printf 'INSTALLED_SOURCE_SHA=%s\n' "$expected_sha"
printf 'DEPLOY_COMMAND=/usr/local/sbin/codestra-middleware-deploy\n'
printf 'BACKUP_COMMAND=/usr/local/sbin/codestra-middleware-backup\n'
printf 'CONFIG_FILE=/etc/codestra-middleware/deploy.conf\n'
printf 'SSH_CONFIGURATION_CHANGED=NO\n'
