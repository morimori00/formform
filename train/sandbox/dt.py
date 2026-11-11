"""Daytona GPU sandbox control for formform training. Run with: uv run --with daytona python train/sandbox/dt.py <cmd>

    capacity                         GPU units free per type (on-demand / spot)
    create [--gpu H100,H200] [--auto-stop 60]   create the GPU sandbox (+ persistent volume), record it in STATE.md
    setup                            install laya + deps, download cklxx/laya-browser (runs remote_setup.sh)
    push LOCAL [REMOTE]              upload a file or directory (tarred) to REMOTE (default /home/daytona/work/<name>)
    pull REMOTE LOCAL                download a file or directory (tarred) from the sandbox
    exec "CMD"                       run a shell command in /home/daytona/work, print output, exit with its code
    start NAME "CMD"                 run CMD in the background; log + rc in /home/daytona/runs/NAME/, copied to the volume when done
    wait NAME [--every 60]           poll a background job (each poll is activity, so auto-stop does not fire), print its tail
    keepalive MINUTES                refresh activity every minute for MINUTES (e.g. while a long job runs unattended)
    status | teardown                show / delete the sandbox (the volume survives)

GPU sandboxes are ephemeral: stop == delete, and auto-stop fires on API inactivity even while processes run.
Finished runs are copied to the volume mounted at /home/daytona/vol (mountpoint-s3: write-once files, no rename),
so train on local disk and copy, never point laya-train --out at the volume directly.
The API key is read from formform/.env at runtime and never printed.
"""

import io
import json
import re
import shlex
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

from daytona import (
    CreateSandboxFromImageParams,
    Daytona,
    DaytonaConfig,
    GpuType,
    Resources,
    VolumeMount,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # formform/
STATE = HERE / "STATE.md"
IMAGE = "pytorch/pytorch:2.11.0-cuda12.8-cudnn9-runtime"
VOLUME = "formform-train"
WORK, VOL, RUNS = "/home/daytona/work", "/home/daytona/vol", "/home/daytona/runs"
ORG = "31a3d67e-0d3e-405b-a76f-50a386bbf8fa"


def key():
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("DAYTONA_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    sys.exit("DAYTONA_API_KEY missing in formform/.env")


def client():
    return Daytona(DaytonaConfig(api_key=key()))


def sandbox_id():
    m = re.search(r"sandbox_id:\s*`?([0-9a-f-]{36})", STATE.read_text()) if STATE.exists() else None
    if not m:
        sys.exit("no sandbox recorded in STATE.md; run create")
    return m.group(1)


def sandbox():
    return client().get(sandbox_id())


def sh(sb, cmd, timeout=3600):
    r = sb.process.exec(f"/bin/bash -c {shlex.quote(f'mkdir -p {WORK} && cd {WORK} && {cmd}')}", timeout=timeout)
    return r.exit_code, r.result


def capacity():
    req = urllib.request.Request(f"https://app.daytona.io/api/organizations/{ORG}/gpu-capacity",
                                 headers={"Authorization": "Bearer " + key()})
    for c in json.load(urllib.request.urlopen(req))["capacity"]:
        print(f"{c['gpuType']:14} on-demand {c['availableOnDemand']:4}  spot {c['availableSpot']:4}")


def create(args):
    gpus = (args[args.index("--gpu") + 1] if "--gpu" in args else "H100,H200").split(",")
    auto_stop = int(args[args.index("--auto-stop") + 1]) if "--auto-stop" in args else 60
    d = client()
    vol = d.volume.get(VOLUME, create=True)
    for _ in range(60):
        if str(vol.state).lower().endswith("ready"):
            break
        time.sleep(2)
        vol = d.volume.get(VOLUME)
    t0 = time.time()
    sb = d.create(CreateSandboxFromImageParams(
        name=f"formform-gpu-{int(t0)}", image=IMAGE, labels={"project": "formform"},
        resources=Resources(cpu=8, memory=32, disk=100, gpu=1, gpu_type=[GpuType(g) for g in gpus]),
        auto_stop_interval=auto_stop, auto_delete_interval=0,
        env_vars={"HF_HOME": "/home/daytona/hf", "PIP_ROOT_USER_ACTION": "ignore", "PYTHONUNBUFFERED": "1"},
        volumes=[VolumeMount(volume_id=vol.id, mount_path=VOL)],
    ), timeout=1800)
    _, gpu = sh(sb, f"mkdir -p {WORK} {VOL}/runs && nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader")
    record(sb.id, gpu.strip(), auto_stop, round(time.time() - t0))
    print(sb.id, gpu.strip())


def record(sid, gpu, auto_stop, secs):
    head = (f"# Daytona GPU sandbox (no secrets here)\n\n- sandbox_id: `{sid}`\n- gpu: {gpu}\n- image: {IMAGE}\n"
            f"- resources: 8 vCPU, 32 GiB RAM, 100 GiB disk, 1 GPU\n- auto_stop_interval: {auto_stop} min (stop == delete for GPU sandboxes)\n"
            f"- volume: `{VOLUME}` mounted at {VOL} (survives the sandbox)\n- created: {time.strftime('%Y-%m-%d %H:%M %Z')} in {secs}s\n")
    rest = STATE.read_text().split("\n## Log", 1)[1] if STATE.exists() and "\n## Log" in STATE.read_text() else "\n"
    STATE.write_text(head + "\n## Log" + rest)


def push(local, remote=None):
    local = Path(local).resolve()
    remote = remote or f"{WORK}/{local.name}"
    sb = sandbox()
    if local.is_file():
        sh(sb, f"mkdir -p {shlex.quote(str(Path(remote).parent))}")
        sb.fs.upload_file(str(local), remote)
        return print("pushed", local, "->", remote)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        t.add(local, arcname=".", filter=lambda i: None if "__pycache__" in i.name or i.name.endswith(".DS_Store") else i)
    tmp = f"/tmp/push-{int(time.time())}.tgz"
    sb.fs.upload_file(buf.getvalue(), tmp)
    code, out = sh(sb, f"mkdir -p {shlex.quote(remote)} && tar xzf {tmp} -C {shlex.quote(remote)} && rm {tmp}")
    print("pushed", local, "->", remote, out if code else "")


def pull(remote, local):
    sb = sandbox()
    local = Path(local)
    _code, kind = sh(sb, f"test -d {shlex.quote(remote)} && echo dir || echo file")
    if kind.strip() == "file":
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(sb.fs.download_file(remote))
        return print("pulled", remote, "->", local)
    tmp = f"/tmp/pull-{int(time.time())}.tgz"
    sh(sb, f"tar czf {tmp} -C {shlex.quote(remote)} .")
    local.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(sb.fs.download_file(tmp)), mode="r:gz") as t:
        t.extractall(local, filter="data")
    sh(sb, f"rm {tmp}")
    print("pulled", remote, "->", local)


def start(name, cmd):
    # Local disk while running: the volume is mountpoint-s3 (no rename/overwrite, files invisible until closed).
    # The finished run dir is copied to the volume afterwards, then rc is written last.
    run = f"{RUNS}/{name}"
    wrapped = (f"mkdir -p {run} && cd {WORK} && ({cmd}) > {run}/log 2>&1; rc=$?; "
               f"mkdir -p {VOL}/runs && cp -r {run} {VOL}/runs/ 2>> {run}/log; echo $rc > {run}/rc")
    # Not through sh(): its "cd && ..." prefix would background a subshell that keeps the exec's stdout open,
    # and the API call would then block until the job ends.
    launch = f"(setsid nohup /bin/bash -c {shlex.quote(wrapped)} > /dev/null 2>&1 < /dev/null &); echo started"
    out = sandbox().process.exec(f"/bin/bash -c {shlex.quote(launch)}", timeout=60).result
    print(out.strip(), run)


def wait(name, every=60):
    sb, run = sandbox(), f"{RUNS}/{name}"
    while True:
        _code, out = sh(sb, f"cat {run}/rc 2>/dev/null; echo ---; tail -n 3 {run}/log 2>/dev/null")
        rc, tail = out.split("---", 1)
        print(time.strftime("%H:%M:%S"), tail.strip().splitlines()[-1:] if tail.strip() else "(no log yet)", flush=True)
        if rc.strip():
            print("exit", rc.strip())
            return int(rc.strip())
        time.sleep(every)


def main(argv):
    cmd, args = (argv[0], argv[1:]) if argv else ("status", [])
    if cmd == "capacity":
        capacity()
    elif cmd == "create":
        create(args)
    elif cmd == "setup":
        push(HERE / "remote_setup.sh", f"{WORK}/remote_setup.sh")
        code, out = sh(sandbox(), f"bash {WORK}/remote_setup.sh", timeout=3600)
        print(out[-4000:])
        sys.exit(code)
    elif cmd == "push":
        push(*args)
    elif cmd == "pull":
        pull(*args)
    elif cmd == "exec":
        code, out = sh(sandbox(), " ".join(args))
        print(out, end="")
        sys.exit(code)
    elif cmd == "start":
        start(args[0], " ".join(args[1:]))
    elif cmd == "wait":
        sys.exit(wait(args[0], int(args[args.index("--every") + 1]) if "--every" in args else 60))
    elif cmd == "keepalive":
        sb = sandbox()
        for _ in range(int(args[0])):
            sb.refresh_activity()
            time.sleep(60)
    elif cmd == "status":
        sb = sandbox()
        print(sb.id, sb.state, "gpu", sb.gpu, "auto_stop", sb.auto_stop_interval)
    elif cmd == "teardown":
        client().delete(sandbox())
        STATE.write_text(STATE.read_text() + f"\n- {time.strftime('%Y-%m-%d %H:%M')} sandbox deleted (teardown)\n")
        print("deleted; volume", VOLUME, "kept")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
