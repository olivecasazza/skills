# First arg: the defining flake's `self` (unused here).
_:
# Second arg: module args from evalModules.
{
  pkgs,
  riglib,
  ...
}:
{
  config.riglets.nixlab-health = {
    meta = {
      description = "Read-only health triage for the nixlab K3s cluster";
      intent = "playbook";
      whenToUse = [
        "When investigating whether the nixlab cluster is healthy"
        "Before/after a deploy, or when a node or workload looks degraded"
      ];
      keywords = [
        "nixlab"
        "kubernetes"
        "k3s"
        "health"
        "triage"
      ];
      status = "draft";
      version = "0.1.0";
    };

    # Read-only triage tooling. Mutations stay out of this skill on purpose.
    tools = [
      pkgs.kubectl
      pkgs.k9s
    ];

    docs = riglib.writeFileTree {
      "SKILL.md" = ''
        # nixlab cluster health triage

        Read-only triage for the nixlab K3s cluster (3-member etcd HA, Cilium CNI,
        Flux GitOps). Never mutate cluster state here — all changes flow through
        Nix → Git → Flux. These commands are safe reads only.

        ## Quick sweep

        ```bash
        kubectl get nodes -o wide
        kubectl get pods -A --field-selector status.phase!=Running,status.phase!=Succeeded
        kubectl get kustomization -A                                  # Flux GitOps reconcile state
        kubectl -n kube-system get pods -l k8s-app=kube-dns -o wide   # CoreDNS (3 replicas)
        kubectl -n ingress logs -l app=cloudflare-tunnel --tail=5     # public ingress
        ```

        ## Reading the results

        - **Nodes**: all `Ready`. A `NotReady` control-plane node (contra/seir/hetzner-cp)
          risks etcd quorum — escalate before touching anything.
        - **Pods**: the field-selector lists only not-Running/Succeeded pods; an empty
          result is healthy. `CrashLoopBackOff`/`ImagePullBackOff` → check that pod's logs.
        - **Flux**: every `Kustomization` should be `Ready=True`. A stuck reconcile means
          pushed changes are NOT live yet.

        ## Escalation

        Cross-node timeouts or etcd flakiness: check seir's wired uplink first — it fails
        over to WiFi when `enp5s0` drops and degrades the control plane.
      '';
    };
  };
}
