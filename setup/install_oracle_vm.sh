#!/usr/bin/env bash
# =============================================================================
# OpenClaw — Oracle Cloud ARM VM Setup Script
# Run this ONCE after provisioning your Always Free ARM instance.
#
# Usage:
#   ssh ubuntu@<vm-ip>
#   git clone https://github.com/<you>/clawdbot /tmp/clawdbot
#   bash /tmp/clawdbot/setup/install_oracle_vm.sh
# =============================================================================
set -euo pipefail

REPO_DIR="${1:-/tmp/clawdbot}"
INSTALL_DIR="/opt/openclaw"
APP_DIR="$INSTALL_DIR/app"
VENV_DIR="$INSTALL_DIR/venv"
SERVICE_USER="openclaw"

echo "==> Updating system packages..."
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y

echo "==> Installing system dependencies..."
sudo apt-get install -y \
    python3.12 python3.12-venv python3-pip \
    git curl nginx certbot python3-certbot-nginx \
    sqlite3 logrotate

echo "==> Creating system user: $SERVICE_USER"
if ! id "$SERVICE_USER" &>/dev/null; then
    sudo useradd --system --shell /bin/false --home-dir "$INSTALL_DIR" "$SERVICE_USER"
fi

echo "==> Creating directory structure..."
sudo mkdir -p "$APP_DIR" "$INSTALL_DIR/data" "$INSTALL_DIR/logs"
sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

echo "==> Copying application files..."
sudo cp -r "$REPO_DIR/." "$APP_DIR/"
sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

echo "==> Creating Python virtual environment..."
sudo -u "$SERVICE_USER" python3.12 -m venv "$VENV_DIR"
sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install --upgrade pip
sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "==> Setting up .env file..."
if [ ! -f "$APP_DIR/.env" ]; then
    sudo cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo ""
    echo "  !! ACTION REQUIRED: Fill in your secrets in $APP_DIR/.env"
    echo "     sudo nano $APP_DIR/.env"
    echo ""
fi

echo "==> Installing systemd service..."
sudo cp "$APP_DIR/setup/systemd/openclaw.service" /etc/systemd/system/
sudo systemctl daemon-reload

echo "==> Configuring logrotate..."
sudo tee /etc/logrotate.d/openclaw > /dev/null <<'EOF'
/opt/openclaw/logs/*.log {
    daily
    rotate 14
    compress
    missingok
    notifempty
    sharedscripts
    postrotate
        systemctl kill -s HUP openclaw.service 2>/dev/null || true
    endscript
}
EOF

echo "==> Opening firewall port 8080 (iptables)..."
sudo iptables -C INPUT -p tcp --dport 8080 -j ACCEPT 2>/dev/null || \
    sudo iptables -A INPUT -p tcp --dport 8080 -j ACCEPT
sudo iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || \
    sudo iptables -A INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null || \
    sudo iptables -A INPUT -p tcp --dport 443 -j ACCEPT

echo ""
echo "================================================================="
echo "  Oracle VM setup complete!"
echo ""
echo "  NEXT STEPS:"
echo "  1. Install Ollama:  bash $APP_DIR/setup/install_ollama.sh"
echo "  2. Edit secrets:    sudo nano $APP_DIR/.env"
echo "  3. Set up HTTPS (pick one):"
echo "     A) DuckDNS + certbot: sudo certbot --nginx -d yourname.duckdns.org"
echo "     B) Cloudflare Tunnel: cloudflared tunnel --url http://localhost:8080"
echo "  4. Start service:   sudo systemctl enable --now openclaw"
echo "  5. Check logs:      sudo journalctl -u openclaw -f"
echo "================================================================="
