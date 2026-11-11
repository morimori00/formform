#!/bin/bash
# One training job in the sandbox: train -> step eval on eval-v1. Usage: bash job.sh NAME TRAIN.jsonl GOAL [laya-train args...]
# Env: GRAD_CKPT=0 turns gradient checkpointing off. Results: /home/daytona/runs/NAME/{ckpt,train.log,eval_steps.json,times}
NAME=$1; DATA=$2; GOAL=$3; shift 3
R=/home/daytona/runs/$NAME; mkdir -p $R; cd /home/daytona/work
T0=$(date +%s)
python ltrain.py --data $DATA --base $(cat BASE_DIR) --out $R/ckpt "$@" > $R/train.log 2>&1 || { tail -3 $R/train.log; exit 1; }
T1=$(date +%s); rm -rf $R/ckpt/checkpoint_latest
ML=4096; for ((i=1; i<=$#; i++)); do [ "${!i}" = "--max-len" ] && { j=$((i+1)); ML=${!j}; }; done
python remote_eval.py $R/ckpt data/eval_$GOAL.jsonl --max-len $ML --out $R/eval_steps.json 2>/dev/null | cut -c1-400
echo "train_s=$((T1-T0)) eval_s=$(( $(date +%s) - T1 )) args=$*" | tee $R/times
