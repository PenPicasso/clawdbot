"""
ClawDBot Deep Analysis — HF Space Inference Server

Loads google/gemma-3-27b-it (4-bit) once at startup.
Exposes /health and /infer for the OpenClaw poller to call.

Fallback: if 27B OOMs, set MODEL_ID env var to google/gemma-3-9b-it
and LOAD_IN_8BIT=true in HF Space settings.
"""

import os
import logging
import torch
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig,
    pipeline,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="ClawDBot Deep Analysis")

# --- Config from HF Space environment variables ---
MODEL_ID = os.environ.get("MODEL_ID", "google/gemma-3-27b-it")
SECRET = os.environ.get("OPENCLAW_SECRET", "")
LOAD_IN_8BIT = os.environ.get("LOAD_IN_8BIT", "false").lower() == "true"
HF_TOKEN = os.environ.get("HF_TOKEN", None)  # needed for gated model access

# --- Load model once at startup ---
logger.info(f"Loading model: {MODEL_ID} (8bit={LOAD_IN_8BIT})")

if LOAD_IN_8BIT:
    bnb_config = BitsAndBytesConfig(load_in_8bit=True)
else:
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, token=HF_TOKEN)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    quantization_config=bnb_config,
    device_map="auto",
    token=HF_TOKEN,
)
pipe = pipeline(
    "text-generation",
    model=model,
    tokenizer=tokenizer,
)

logger.info("Model loaded and ready.")


# --- Request/response schemas ---
class InferRequest(BaseModel):
    prompt: str
    max_tokens: int = 1024
    temperature: float = 0.7


class InferResponse(BaseModel):
    result: str
    model: str


# --- Endpoints ---
@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_ID}


@app.post("/infer", response_model=InferResponse)
def infer(
    req: InferRequest,
    x_openclaw_secret: str = Header(default=""),
):
    if SECRET and x_openclaw_secret != SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    logger.info(f"Inference request: {len(req.prompt)} chars")

    outputs = pipe(
        req.prompt,
        max_new_tokens=req.max_tokens,
        do_sample=True,
        temperature=req.temperature,
        top_p=0.9,
        return_full_text=False,
    )

    result = outputs[0]["generated_text"].strip()
    logger.info(f"Inference complete: {len(result)} chars output")

    return InferResponse(result=result, model=MODEL_ID)
