# ClawDBot Phase 2 Deployment Guide

## Pre-Deployment Checklist

- [ ] All code committed and pushed to GitHub
- [ ] .env updated with new variables
- [ ] Database migration tested locally (if possible)
- [ ] All imports verified (no missing dependencies)
- [ ] Rate limit values reviewed for production
- [ ] ADMIN_SECRET set to strong random value

## Environment Variables to Add

Add these to `.env` on the Oracle VM:

```env
# Phase 2: Rate Limiting
RATE_LIMIT_COMPLEX_PER_HOUR=5
RATE_LIMIT_MEDIUM_PER_HOUR=20
RATE_LIMIT_GLOBAL_PER_HOUR=20

# Phase 2: Admin Secret (required for /logs endpoint)
ADMIN_SECRET=<generate-strong-random-string>

# Phase 2: Extended HF timeout for deep analysis
HF_INFER_TIMEOUT=600
```

### Generate ADMIN_SECRET
```bash
# On Linux/Mac
openssl rand -hex 32

# On Windows PowerShell
[Convert]::ToHexString((1..32|ForEach-Object{Get-Random -Max 256}))
```

## Deployment Steps

### 1. Pull Latest Code
```bash
cd /opt/openclaw/app
git pull origin master
```

### 2. Update .env
```bash
nano .env  # Add the 3 new variables above
```

### 3. Restart FastAPI Service
```bash
# Kill the existing process
pkill -f "python.*main.py"

# Start new process (or use systemd/supervisor as configured)
python main.py &
```

### 4. Verify Startup
```bash
curl http://localhost:8000/health
# Should return: {"status": "ok", "ollama": "up", "pending_jobs": 0, ...}
```

## Testing Workflow (on phone via Telegram)

### Test 1: Simple Message
```
Send: "hi"
Expected: Immediate reply within ~2 seconds
```

### Test 2: Medium Message
```
Send: "explain how blockchain works in simple terms"
Expected: 
  - Immediate ACK: "Queued for analysis (position 1 in queue) · est. 2–5 min"
  - Message edits in ~30–90 seconds with result
```

### Test 3: Complex Message
```
Send: "analyze pros and cons of nuclear vs renewable energy, with cost comparison"
Expected:
  - Immediate ACK: "Queued for deep research · est. 10–15 min"
  - Message edits in ~5–15 minutes
  - Result shows structured analysis (PLAN, iterations, critique feedback)
```

### Test 4: Rate Limiting
```
Send 6 complex messages in quick succession
Expected: 6th message blocked with:
  "⏸ Complex job limit reached (5/hour). Try /ask for a faster response."
```

### Test 5: Admin Commands (as admin only)
```
/logs
Expected: Last 5 agent runs with task_type, status, elapsed time, score

/teach energy | Nigeria has ~4GW installed capacity as of 2025
Expected: "Knowledge: stored"

/teach private_key | sk-abc123xyz
Expected: "Knowledge: rejected: content contains sensitive information"

/budget
Expected: Budget config (simple=15s, medium=90s, complex=900s) + recent timings
```

### Test 6: HTTP Logs Endpoint
```bash
curl -H "X-Admin-Secret: $ADMIN_SECRET" \
  "http://localhost:8000/logs?limit=5&task_type=complex"

# Should return JSON with runs and summary stats
```

## Monitoring & Troubleshooting

### Check Queue Status
```bash
curl http://localhost:8000/health
# Look at: pending_jobs count
```

### View Recent Agent Runs
```bash
curl -H "X-Admin-Secret: $ADMIN_SECRET" \
  "http://localhost:8000/logs?limit=10"
```

### Check Logs
```bash
tail -f /var/log/openclaw/app.log
# Look for: agent loop timings, HF warm-up, rate limit checks
```

### Common Issues

**Issue**: "HF Space warming up, waiting 60s"
- Normal behavior before complex jobs if Space was idle
- Indicates Space cold-start, expected once every few hours

**Issue**: Complex job times out after 900s
- Budget exceeded, check if HF Space is overloaded
- Message will show: "[Analysis stopped: 900s budget]"
- Result is partial but user still gets it

**Issue**: Rate limit rejections
- Check /logs endpoint to see recent job counts
- Adjust RATE_LIMIT_*_PER_HOUR in .env if needed

**Issue**: Agent loop fails to complete
- Check logs for hf_infer() errors
- Fallback should trigger after 3 retries, returning fast_complete() result
- If both fail, user gets: "Sorry, both models are currently unavailable..."

## Rollback Plan

If issues arise:

1. **Revert to Phase 1**:
   ```bash
   git revert HEAD
   pkill -f "python.*main.py"
   python main.py &
   ```

2. **Keep Phase 2A but disable agent loop**:
   - In poller.py, replace `agent.run()` call with direct `models.hf_infer()`
   - Keeps classifier/rate_limit/memory but skips adaptive loop

3. **Clear job queue**:
   ```bash
   sqlite3 /opt/openclaw/data/jobs.db \
     "DELETE FROM jobs WHERE status IN ('pending', 'processing', 'failed')"
   ```

## Performance Baselines

Expected timing (from Phase 2A testing):

- **Simple message**: <2s (4B model)
- **Medium message**: 5–90s (4B loop: PLAN + EXECUTE + TEST)
- **Complex message**: 10–900s (27B PLAN + 4B loop + 27B CRITIQUE, max 2 deep calls)

If timings exceed these by 2x, likely issues:
- HF Space overloaded (check /health)
- Ollama (4B) slow on VM
- Network latency (rare)

## Production Monitoring

Set up alerts for:
1. `/health` endpoint response time > 5s
2. Agent runs with status='failed' (falling back to fast model)
3. Rate limit rejections > 10/hour (capacity issue)
4. Pending jobs > 5 (queue backing up)

## Post-Deployment Validation

After 24 hours of running:
1. Check /logs for mix of simple/medium/complex completions
2. Verify no stuck jobs (all have final status)
3. Confirm memory system working (conversation history growing)
4. Validate rate limiter (check for rejections during heavy usage)
5. Review agent run scores (target: 7+ for approved runs)

---

**Questions?** Check PHASE2_CODEX.md for architecture, or openclaw/*.py for specific implementation details.
