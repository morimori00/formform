"""laya-train with PyTorch's cuDNN attention backend off (sandbox): `python ltrain.py <laya-train args>`.

torch 2.11 routes scaled_dot_product_attention through cuDNN on this GPU, which plans a new graph for every unseen
sequence shape (~1 s each, GPU idle). Form requests vary from 400 to 3,200 tokens, so almost every batch is a new shape:
measured 900-1,300 ms per decision with it on vs 17-70 ms with it off.
"""
import sys

import torch

torch.backends.cuda.enable_cudnn_sdp(False)
from laya.train_cli import main  # noqa: E402

sys.exit(main())
