
## Facts 6 and 7, added 2026-09-10 and registered again 2026-09-26: the cage, on the same sample

Ecosystem ticket 86, from ticket 75 Q8 (the owner's answer, delegated: the lane branch), registered
again by ecosystem ticket 152 (delegated, 2026-09-25) and built by ticket 161. Pre-registered in
[`window.yaml`](window.yaml) under `cage_behaviour_sample`, and taken by the same scheduled run, on
the same cluster, in the same record as the five.

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
| 7 | That workload completes **neither** a TCP connection to the API server **nor** one outside the cluster, and its rung is the ladder's bottom by its priority and by a reach policy with no rules, while a **reference workload** that the cage does not select completes both. A connection, never a read of the NetworkPolicy's own YAML. |

**The rung is the cage's answer, not the instrument's.** Two namespaces are created, and neither
names a tier. One is `governed` with no tier, so the cage's own fall-closed rule decides where its
pod lands. The instrument then checks that the landing place is the ladder's **bottom**, from what
the cluster serves and not from a name typed here: the pod's priority is the lowest of the `cage-`
PriorityClasses on the cluster, and the NetworkPolicy that selects it has no ingress rule, no
egress rule, and declares both policy types. If either check fails, facts 6 and 7 both read
could-not-look, because each names the bottom rung and a TRUE would name a rung the cage did not
use. Nothing here types the word `isolated`.

**The reference workload is outside the cage.** The other Namespace carries no governed label and
no tier, and its pod claims no policy version, so the cage does not select it (ecosystem 119,
decision 2). It runs the same image and the same two connects, and it is read **before and after**
the bottom-rung pod, so a working network brackets the silence. Until 2026-09-26 the comparison pod
was a "control" that claimed a version in an ungoverned Namespace; under 5.0.0 the cage put it on
`isolated` beside the fall-closed pod, and fact 7 read null on every sample (ticket 152). A pod on a
looser rung that the sampler declared at run time was considered and refused: it would buy a cage
no signed declaration chose, which ADR-0022 calls an exemption. In this estate a **control** is a
catalogue control, so the word is not used for this pod.

**The reference is what stops a false green.** A pod that reaches nothing because the cluster is
broken must not read the same as a pod that reaches nothing because the cage holds. So a run where
the reference reaches nothing either is recorded UNMEASURED — a declared falsifier, never a pass.
Same for a cage that selects the reference: a tier or caged label on it, or a NetworkPolicy that
selects it, and the reference is not a reference.

**A null that never clears is a fall.** A cage fact that is null on each of the three newest samples
taken since the registration fires `the_cage_facts_stay_unmeasured`, and `grade` reports FAIL naming
the fact and its reason. A null that clears on the next sample stays a could-not-look. Samples from
before the registration do not count, so the rule can first fire on the third sample after it.
`grade`'s SKIP line names every null fact and its reason.

**The sidecar is a stand-in and the fact says so.** The cage injects `ghcr.io/acme/coraza-waf:cage`
at every hardened rung and that image exists in no registry. The workflow builds platform's own
`graded/waf-placeholder` — out of the tree already checked out at the tag this repo pins — under
that name and loads it into the node. A sleeping busybox is not a WAF: fact 6 proves the caged
workload *runs* with what the cage added, not that anything inspected traffic.

**Pre-registration is measured, not asserted.** `grade` walks first-parent history on the served
ref and reads the newest commit that changed the entire `cage_behaviour_sample` section in
`window.yaml`, including its question, facts, falsifiers, ceilings and comments. A sample taken
before that change reads could-not-look on facts 6 and 7, on a line that names the commit: a
question not yet asked is never a pass, and a sample from before a re-registration never prints
PASS on five facts (ticket 152 Q4). A branch commit registers nothing. Rewriting the section
re-registers it, and scores against the previous wording stop counting (ticket 93); changes outside
the section do not re-register these facts.

**The served documents are proven offline too.** [`../verify-cage-probe.sh`](../verify-cage-probe.sh)
runs `five-facts.py selfcheck`, checks the kyverno CLI against the engine this repository declares
(`gitops/engine/kyverno.yaml`, or `KYVERNO_VERSION` in `drift-sample.yml` until that file exists),
proves the CLI reads Namespace labels, and runs the sampler's own probe objects against the served
composed set at the pinned tag and at HEAD: the fall-closed pod must land on the bottom (lowest
`cage-` PriorityClass, a selecting NetworkPolicy with no rules and both types), nothing may select
the reference pod, and every PriorityClass a mutation names must be served. Its PASS is about the
documents; the lane's facts are about the cluster, and the two do not conflict. It runs on every
pull request (`shift-left.yml`) and in the hub's gate.
