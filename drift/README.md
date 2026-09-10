
## Facts 6 and 7, added 2026-09-10: the cage, on the same sample

Ecosystem ticket 86, from ticket 75 Q8 (the owner's answer, delegated: the lane branch).
Pre-registered in [`window.yaml`](window.yaml) under `cage_behaviour_sample`, and taken by the same
scheduled run, on the same cluster, in the same record as the five.

The estate's most distinctive claim is that **nothing is denied**: a workload that does not fit its
cage runs on a tighter rung, and the bottom rung runs and reaches nothing. That claim had never been
graded PASS on a citable run. The instrument that observes it — platform's `graded/verify-graded.sh`
live tail — needs a persistent KinD cluster the scheduled truth runner has never created, so it has
exited 3 on every run since run 15; the runs that *do* observe the cage are presenter runs on a
laptop, and NORTH-STAR §5 forbids citing those. This lane already brings up a real cluster per run.
So the claim is graded here.

| Fact | What it observes |
|---|---|
| 6 | The workload the cage places on its **own bottom rung** is admitted by the API server and reaches Running. A refusal is quoted verbatim; a pod admitted and never started is observed false, because a cage that does not run the workload is a refusal with extra steps. |
| 7 | That workload completes **neither** a TCP connection to the API server **nor** one outside the cluster, while a control workload the cage left loose completes both. A connection, never a read of the NetworkPolicy's own YAML. |

**The rung is the cage's answer, not the instrument's.** Two namespaces are created, and neither
names a tier. One is `governed` with no tier, so the cage's own fall-closed rule decides where its
pod lands; the other is not governed, so the cage puts its pod on the loosest rung. What the cage
stamped is read back off each pod. Nothing here types the word `isolated`.

**The control is what stops a false green.** A pod that reaches nothing because the cluster is
broken must not read the same as a pod that reaches nothing because the cage holds. So a run where
the control reaches nothing either is recorded UNMEASURED — a declared falsifier, never a pass.
Same for a cage that puts both pods on the same rung: there is then no bottom rung to look at.

**The sidecar is a stand-in and the fact says so.** The cage injects `ghcr.io/acme/coraza-waf:cage`
at every hardened rung and that image exists in no registry. The workflow builds platform's own
`graded/waf-placeholder` — out of the tree already checked out at the tag this repo pins — under
that name and loads it into the node. A sleeping busybox is not a WAF: fact 6 proves the caged
workload *runs* with what the cage added, not that anything inspected traffic.

**Pre-registration is measured, not asserted.** `grade` walks first-parent history on the served
ref and reads the newest commit that changed the entire `cage_behaviour_sample` section in
`window.yaml`, including its question, facts, falsifiers, ceilings and comments. Neither fact is
scored against a sample taken before that change. A branch commit registers nothing. Rewriting
the section re-registers it, and scores against the previous wording stop counting (ticket 93);
changes outside the section do not re-register these facts.
