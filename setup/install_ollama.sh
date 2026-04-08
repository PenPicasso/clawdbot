#!/usr/bin/env bash
# =============================================================================
# OpenClaw — Ollama + Gemma E4B Setup
# Run this AFTER install_oracle_vm.sh
#
# Usage:
#   bash /opt/openclaw/app/setup/install_ollama.sh
# =============================================================================
set -euo pipefail

MODEL="${1:-gemma3:4b}"

echo "==> Installing Ollama..."
curl -fsSL https://ollama.com/install.sh | sh

echo "==> Enabling Ollama service..."
sudo systemctl enable ollama
sudo systemctl start ollama

echo "==> Waiting for Ollama to be ready..."
for i in {1..10}; do
    if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "    Ollama is up."
        break
    fi
    echo "    Waiting... ($i/10)"
    sleep 3
done

echo "==> Pulling model: $MODEL (~2.5GB, may take a few minutes)..."
ollama pull "$MODEL"

echo "==> Verifying model..."
RESPONSE=$(ollama run "$MODEL" "Reply with exactly: OK" 2>&1 || true)
echo "    Model response: $RESPONSE"

echo ""
RAM_USED=$(ollama ps 2>/dev/null | grep "$MODEL" | awk '{print $3}' || echo "unknown")
echo "================================================================="
echo "  Ollama setup complete!"
echo "  Model: $MODEL"
echo "  Ollama API: http://localhost:11434"
echo ""
echo "  Memory info:"
free -h
echo ""
echo "  Test inference:"
echo "    ollama run $MODEL 'Hello!'"
echo "================================================================="
