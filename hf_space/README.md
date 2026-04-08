---
title: ClawDBot Deep Analysis
emoji: 🔬
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
---

# ClawDBot Deep Analysis — HF Space

This Space runs the **Gemma 3 27B** inference server for the ClawDBot system.
It exposes a minimal FastAPI REST API (not Gradio) consumed by the OpenClaw backend.

## Endpoints

- `GET /health` — liveness check
- `POST /infer` — run inference; requires `X-OpenClaw-Secret` header

## Setup

Set the `OPENCLAW_SECRET` environment variable in Space Settings → Variables
before the first build. The Oracle VM backend must use the same value.

## Hardware

CPU Basic (free tier). Cold-start takes 8–20 minutes (model download).
The OpenClaw poller sends a keep-alive ping every 4 minutes to prevent sleep.
