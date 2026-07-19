#!/usr/bin/env bash
#
# One-time VPS provisioning for the KYC-API production host (Ubuntu 24.04).
#
# Run as root, ONCE, on a fresh box:
#     scp scripts/provision_vps.sh root@HOST:/root/
#     ssh root@HOST 'bash /root/provision_vps.sh'
#
# Idempotent: safe to re-run. It installs Docker, a firewall, automatic
# security updates, fail2ban and a non-root `deploy` user — but deliberately
# does NOT touch SSH password auth or root login. Locking those down is a
# separate manual step you take ONLY after confirming key-based login works
# (see docs/DEPLOYMENT.md), because getting the order wrong locks you out of
# your own server.
set -euo pipefail

DEPLOY_USER=deploy
APP_DIR="/home/${DEPLOY_USER}/kyc-api"

echo "==> apt update + security upgrades"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

echo "==> base packages (firewall, auto-updates, fail2ban, time sync)"
apt-get install -y \
    ufw \
    unattended-upgrades \
    fail2ban \
    chrony \
    curl \
    ca-certificates

echo "==> Docker Engine + compose plugin (official convenience script)"
if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

echo "==> non-root deploy user"
if ! id -u "${DEPLOY_USER}" >/dev/null 2>&1; then
    adduser --disabled-password --gecos "" "${DEPLOY_USER}"
fi
# docker: run compose without sudo; sudo: occasional host admin.
usermod -aG docker,sudo "${DEPLOY_USER}"
# Passwordless sudo for the deploy user. It's created without a password (so
# nobody can log in as it with one), which would otherwise make `sudo` prompt
# for a password it doesn't have. This does not lower security: membership in
# the docker group already grants root-equivalent access via the daemon.
echo "${DEPLOY_USER} ALL=(ALL) NOPASSWD:ALL" >"/etc/sudoers.d/90-${DEPLOY_USER}"
chmod 440 "/etc/sudoers.d/90-${DEPLOY_USER}"
install -d -o "${DEPLOY_USER}" -g "${DEPLOY_USER}" -m 700 "/home/${DEPLOY_USER}/.ssh"
install -d -o "${DEPLOY_USER}" -g "${DEPLOY_USER}" -m 750 "${APP_DIR}"

echo "==> firewall: allow only SSH + HTTP(S)"
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw default deny incoming
ufw default allow outgoing
# --force so enabling over SSH doesn't prompt; 22 is already allowed above,
# so the current session survives.
ufw --force enable

echo "==> automatic security updates"
# Non-interactive equivalent of dpkg-reconfigure -plow unattended-upgrades.
cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

systemctl enable --now fail2ban
systemctl enable --now chrony

cat <<EOF

==> Provisioning done.

WARNING — Docker publishes container ports straight into iptables, BYPASSING
ufw. The production compose only publishes Caddy (80/443) and keeps Postgres
on the internal network with no host port. Never add a 'ports:' mapping to the
db service — it would expose the database to the internet despite the firewall.

Next, follow docs/DEPLOYMENT.md:
  1. Install your SSH public key into /home/${DEPLOY_USER}/.ssh/authorized_keys
     and confirm you can log in as ${DEPLOY_USER} BEFORE disabling password auth.
  2. Copy the prod compose + Caddyfile into ${APP_DIR}, write the .env there.
  3. Add the GitHub 'production' environment secrets, push, let CI build and
     deploy.
EOF
