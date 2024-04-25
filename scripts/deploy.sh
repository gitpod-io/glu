#!/usr/bin/env bash
set -eu

# Required environment variables:
## CONFIG_BASE4
## SSH_LOGIN
## SSH_PRIVATE_KEY_BASE64

# Deploy function runs inside the remote server
function deploy() {
	set -x
	local app_dir="/app3"
	local systemd_service_name="glu-bot"
	local repo_link="https://github.com/axonasif/glu.git"

	# Get rid of bloat
	for i in apt-daily.timer update-notifier-download.timer update-notifier-motd.timer; do
		systemctl disable $i
		systemctl stop $i
	done
	apt purge -yq snapd unattended-upgrades

	# Install systemd service units
	cat >"/etc/systemd/system/${systemd_service_name}.service" <<EOF
[Unit]
Description=Glu Bot
After=network.target

[Service]
ExecStartPre=sh -c 'git reset --hard && git pull --ff && poetry install'
ExecStart=doppler --config-dir /root/.doppler run --mount BotConfig.toml --mount-template BotConfig_tmpl.toml --mount-max-reads 1 -- poetry run python3 -m glu
Restart=always
WorkingDirectory=${app_dir}

[Install]
WantedBy=multi-user.target

EOF

	if ! test -e "${app_dir}"; then {
		git clone "${repo_link}" "${app_dir}"
		cd "${app_dir}"

	}; fi

	base64 -d <<<"${CONFIG_BASE64}" >"${app_dir}/BotConfig.toml"

	systemctl daemon-reload
	systemctl enable "${systemd_service_name}"

	systemctl stop "${systemd_service_name}"
	systemctl start "${systemd_service_name}"
}

# Runs on host machine
##
private_key=/tmp/.pkey
if test ! -e "${private_key}"; then {
	base64 -d <<<"${SSH_PRIVATE_KEY_BASE64}" >"${private_key}"
	chmod 0600 "${private_key}"
}; fi

ssh_cmd=(
	ssh -i "${private_key}"
	-o UserKnownHostsFile=/dev/null
	-o StrictHostKeyChecking=no
	"${SSH_LOGIN}"
)

printf '%s\n' \
	CONFIG_BASE64"=${CONFIG_BASE64}" \
	"$(declare -f deploy)" \
	"deploy" | "${ssh_cmd[@]}" -- bash
