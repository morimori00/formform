#!/bin/bash
# Runs inside the GPU sandbox (dt.py setup). Idempotent: safe to rerun on a fresh sandbox.
set -euo pipefail
cd /home/daytona/work
export PIP_BREAK_SYSTEM_PACKAGES=1  # throwaway container; keeps the image's CUDA torch
python -m pip install -q "laya>=0.4.31" "transformers>=4.48" huggingface_hub safetensors
# Base model (v19s, laya checkpoint at the repo root) + its request builder and one recorded jev step.
python - <<'EOF'
from huggingface_hub import snapshot_download
d = snapshot_download("cklxx/laya-browser", allow_patterns=[
    "rl_agent_config.json", "model.safetensors", "tokenizer/*", "encoder/*",
    "code/apps/laya_browser.py", "code/sample_request.json"])
print("model dir", d)
open("/home/daytona/work/BASE_DIR", "w").write(d)
EOF
D=$(cat /home/daytona/work/BASE_DIR)
cp "$D/code/apps/laya_browser.py" "$D/code/sample_request.json" /home/daytona/work/
python - <<'EOF'
import json, time, torch, laya, transformers
from laya_browser import LayaBrowser
print("torch", torch.__version__, "cuda", torch.cuda.is_available(), torch.cuda.get_device_name(0))
print("laya", getattr(laya, "__version__", "?"), "transformers", transformers.__version__)
lb = LayaBrowser.from_pretrained("cklxx/laya-browser", device="cuda")
body = json.load(open("sample_request.json"))
for _ in range(3):
    t = time.perf_counter(); a = lb.systemone(body)["answers"]; ms = (time.perf_counter() - t) * 1000
op = a["operation"]["choice"]
tq = op.lower() + "_target"
print("verify: operation", op, round(a["operation"]["confidence"], 3),
      "target", a[tq]["choice"] if tq in a else None, f"{ms:.0f} ms (warm)")
EOF
nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader
echo SETUP_OK
