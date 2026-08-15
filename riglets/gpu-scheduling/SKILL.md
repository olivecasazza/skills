---
name: gpu-scheduling
description: How to place GPU work on the nixlab cluster — Kueue lanes, resident services, SkyPilot, and the capacity map
---

# GPU scheduling on nixlab

One rule, three lanes. **Batch GPU work goes through Kueue. Resident GPU
services get an explicit node pin and a documented quota carve-out.
Interactive work (SkyPilot) uses leftover capacity and must idle-down.**
Never point a raw pod at a GPU node outside these lanes.

## Capacity map (2026-08)

| Node | GPUs | Access path |
|---|---|---|
| hp01-03 | 3x RTX 4000 (8 GB), autoscale-to-zero | Kueue `hp-gpu` (rtx4000 flavor) or SkyPilot |
| seir | 2x RTX 5000 (16 GB) | 1 reserved (comfyui webui); 1 via Kueue `hp-gpu` (rtx5000 flavor) |
| tyan01 | 8x GTX Titan Black (6 GB, Kepler, CUDA <= 11.4) | 1 reserved (tei); 7 via Kueue `kepler-gpu` |
| traitor | 1x RX 7900 XTX (ROCm gfx1100) | reserved (tei-amd); no queue — single card |
| contra | 1x RTX 4000 SFF Ada | reserved (Plex transcode); NEVER schedule GPU work here |

Source of truth for queues/quotas: `nixlab/modules/k8s/kueue/queues.nix`.

## Lane 1 — scheduled batch (Kueue)

LocalQueues → ClusterQueues:

| LocalQueue | Namespace | ClusterQueue | Hardware |
|---|---|---|---|
| `athena-gpu` | apps | `hp-gpu` | RTX 4000 x3 + RTX 5000 x1 |
| `spot-gpu` | hpc | `hp-gpu` | same shared quota |
| `athena-kepler` | apps | `kepler-gpu` | Titan Black x7 |
| `spot-kepler` | hpc | `kepler-gpu` | same shared quota |

How to submit:
- **athena Experiment/BenchmarkRun**: set `spec.scheduling.queueName` on the
  RuntimeProfile. The operator stamps the label and creates the Job suspended.
  A GPU profile without `queueName` is a review-blocking defect.
- **Raw batch/v1 Job**: label `kueue.x-k8s.io/queue-name: <localqueue>` and
  create with `spec.suspend: true` (see `imgen-submit.py` for the canonical
  shape, including `kueue.x-k8s.io/priority-class`).
- **RayJob**: the queue-name label alone is enough — Kueue's ray.io/rayjob
  integration manages suspension.

Mechanics worth knowing:
- Admission is **quota-based, not node-based**: a job is admitted even when
  hp01-03 are powered off; the pending pod triggers cluster-autoscaler →
  hephaestus IPMI power-on (~5-6 min to first pod start). Never "fix" a
  5-minute Pending pod by adding nodeSelectors.
- Kueue injects the admitted flavor's nodeLabels (and, for `kepler`, the
  tyan01 taint tolerations) into the pods — producers don't hand-place.
- Kepler lane needs CUDA <= 11.4 / sm_35-capable images (driver 470).
  Modern PyTorch wheels will not initialize — use the queue only with
  images built for it.
- Never pin GPU-less pods (Ray heads, dashboards, viewers) to hp01-03 —
  that keeps a server powered 24/7. CPU-only podsets fall into the
  `cpu-any` flavor automatically.
- Priorities: `mesh-high` preempts within `hp-gpu`; `imgen-low` yields.

## Lane 2 — resident GPU services

comfyui (seir), tei (tyan01), tei-amd (traitor), Plex (contra). Rules when
adding or moving one:
- Explicit `nodeSelector` on `kubernetes.io/hostname` + the node's GPU
  taint tolerations. No floating `gpu.present=true` selectors — a drifting
  service silently breaks quota math.
- `strategy.type: Recreate` — a single-GPU node deadlocks RollingUpdate
  (the new pod can never schedule while the old one holds the card).
- In the SAME commit, update the affected flavor's `nominalQuota` and the
  reservation comment in `nixlab/modules/k8s/kueue/queues.nix`.
  Invariant: flavor GPU quota = physical GPUs − resident reservations.

## Lane 3 — on-demand interactive (SkyPilot)

`sky api login -e https://skypilot.casazza.io`. SkyPilot pods bypass Kueue
entirely and compete with admitted jobs for the same free GPUs, so:
- Interactive/dev sessions only. Anything unattended belongs in Lane 1.
- Always `-i 60 --down` (the skypilot-env launch scripts default this);
  a forgotten cluster squats a GPU Kueue believes is free.
- Valid on-prem accelerators: `QUADRO-RTX4000`, `QUADRO-RTX5000` only.
  tyan01 and traitor are unreachable from SkyPilot.

## Plex / media transcode

Plex holds contra's GPU via `runtimeClassName: nvidia` device access with
NO `nvidia.com/gpu` resource request (deliberate — non-exclusive). contra
has no `gpu.product` label, so no Kueue flavor can ever place work there.
Keep it that way.

## Verify

```bash
kubectl get clusterqueues,localqueues -A            # queues + admitted counts
kubectl get workloads -A | tail -20                 # recent admissions
kubectl describe clusterqueue hp-gpu | grep -A20 "Flavors Usage"   # live quota usage
kubectl get pods -A -o json | jq -r '.items[] | select(.status.phase=="Running") | select([.spec.containers[].resources | (.limits["nvidia.com/gpu"] // .limits["amd.com/gpu"])] | any(. != null)) | [.metadata.namespace,.metadata.name,.spec.nodeName] | @tsv'   # who holds GPUs now
```

A job stuck suspended = queue name typo or quota exhausted
(`kubectl describe workload <name>` shows which). A GPU "free" in nvidia-smi
but unadmittable = a resident service reservation — check the capacity map.

