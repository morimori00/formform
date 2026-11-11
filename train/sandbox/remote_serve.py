"""Decision server (runs in the sandbox): the local eval loop posts one decision request per browser step.

    python remote_serve.py [port=8791]
    POST / {"model": <laya.load id or checkpoint dir>, "max_len": 4096, "state": ..., "questions": ...} -> {"answers": ...}

Models load on first use and stay loaded. Requests are in convert_to_laya.build_request format and are answered with
predict_chunked (choices wider than 60 options), exactly like remote_eval.py.
"""

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import laya
import torch
from convert_to_laya import predict_chunked

torch.backends.cuda.enable_cudnn_sdp(False)  # cuDNN attention re-plans per sequence shape: ~1 s per new length (see ltrain.py)
AGENTS, LOCK = {}, threading.Lock()


def agent_for(name):
    if name not in AGENTS:
        agent = laya.load(name, device="cuda")
        agent.cfg["head_max_len"] = max(768, agent.cfg.get("head_max_len_train", agent.cfg.get("head_max_len", 0)))
        try:  # ModernBERT would torch.compile its embeddings on first use
            agent.model.encoder.config.reference_compile = False
        except AttributeError:
            pass
        AGENTS[name] = agent
    return AGENTS[name]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send(200, {"ok": True, "loaded": list(AGENTS)})

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            with LOCK:  # one GPU, one forward pass at a time
                agent = agent_for(body["model"])
                agent.cfg["max_len"] = int(body.get("max_len") or agent.cfg["max_len"])
                started = time.perf_counter()
                answers = predict_chunked(agent, body["state"], body["questions"])
            self._send(200, {"answers": answers, "model": body["model"], "latency_ms": round((time.perf_counter() - started) * 1000, 1)})
        except Exception as e:  # the loop treats a failed decision as an episode error
            self._send(400, {"error": f"{type(e).__name__}: {e}"[:500]})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8791
    print(f"serving on :{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
