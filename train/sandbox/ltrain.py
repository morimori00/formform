"""laya-train with PyTorch's cuDNN attention backend off (sandbox): `python ltrain.py <laya-train args>`.

torch 2.11 routes scaled_dot_product_attention through cuDNN on this GPU, which plans a new graph for every unseen
sequence shape (~1 s each, GPU idle). Form requests vary from 400 to 3,200 tokens, so almost every batch is a new shape:
measured 900-1,300 ms per decision with it on vs 17-70 ms with it off.
"""
import os
import sys

import torch

torch.backends.cuda.enable_cudnn_sdp(False)
import laya.train  # noqa: E402
from laya.train_cli import main  # noqa: E402

if os.environ.get("GRAD_CKPT") == "0":  # laya-train has no flag for it; on by default with CUDA (slower, less memory)
    _train_model = laya.train.train_model

    def train_model(model, tok, items, config, *args, **kwargs):
        config.gradient_checkpointing = False
        return _train_model(model, tok, items, config, *args, **kwargs)

    laya.train.train_model = train_model

sys.exit(main())
