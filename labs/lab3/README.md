# Lab 3 — Preview. Do not publish.

**Source/mock development candidate, not native acceptance.** Linux AMD64 and
ARM64 must be qualified separately. Preparation/Lab 1/Lab 2 results do not qualify
nested OpenShell enforcement, provider cleanup or this storage topology.

Prepare a conference-menu Preview while OpenShell enforces a publication boundary.
The host Controller runs one prepared task. Browser pages and native OpenShell
logs provide independent evidence. The Editor contains a public walkthrough.
The intentionally over-scoped preview helper is a teaching asset, not production
publishing software.

## Output and diagnostics

Every Lab 3 action accepts `-v` or `--verbose` after the action, for example
`./lab.sh lab3 run-pipeline --verbose`. Default output keeps the result, safe
next action and all START/STOP, cost, consent and provider-settlement warnings.
Verbose adds authored stage details; it never dumps credentials, arbitrary
private subprocess output or raw exception payloads. Exercise instructions and
interactive application output remain visible in both modes.

Next actions are highlighted on supported terminals. `NO_COLOR` (including an
empty value), dumb terminals and redirected output disable colour. RESET advice
includes a data-loss warning. Verbose does not bypass settlement or make an
uncertain operation safe to retry; never replay START for debugging.

## Prerequisites and setup

Complete workshop preparation on the same local Linux Docker engine. Lab 3 needs
host networking and at least two engine-reported CPUs for its OpenShell/Editor
UI. Rootless/user-namespace engines and Docker Desktop host networking require
explicit platform qualification. No architecture emulation/fallback is selected.
Use **one lab at a time**; do not overlap setup, activation, stop, reset, removal
or image mutations. This is an operator precondition, not global serialization.

```bash
./lab.sh build-labs
./lab.sh lab3 setup
```

`build-labs` prepares public Lab 1/2/3 software only. It does not set up lab storage,
read preparation credentials, start services or call models. Shared tooling may
download pinned public software. Lab compositions use cached preparation parents
and network-disabled builds. Existing owned mutable images receive retained tags;
a build does not upgrade an existing environment or prune cache.

`lab3 setup` prepares software for a fresh selection, initializes private mTLS,
client configuration and synthetic site data, and creates **stopped** resources.
It does not start the gateway, create a sandbox, enroll a provider or call a model.
Public build progress goes to the private workshop `lab-log.txt`; use
`./lab.sh lab3 setup --verbose` to see safe build progress.

The client endpoint and engine-side socket path differ on VM-backed engines.
Only for a separately qualified nondefault engine-side source:

```bash
./lab.sh lab3 setup --engine-socket /ENGINE/SIDE/docker.sock
```

Do not use a macOS client socket path or guess a group ID. Only the trusted
gateway mounts the selected engine socket. Its bootstrap requires socket mode
0660, identifies its group, irreversibly drops root UID/GID and verifies access.
There is no chmod, root fallback or broader driver/workload mount.

## Terminal 1 — activate, inspect, then START

```bash
./lab.sh lab3 run-pipeline
```

This consumes one finite activation window and starts the **recorded** environment
and provider-free sandbox. It never substitutes today's rebuilt workload tag or
Pi files. It prints actual loopback Preview/Live URLs, the sandbox name, installed
task, supplier facts and policy walkthrough. Open **both** pages: each starts with
**Iced Coffee** and **Hot Matcha**, both **฿60**. Record Live's content revision and
publication time, and Preview's revision and build time; refresh both and confirm
reading does not advance those details.
**No credential enrollment or model task occurs before START.**
Ports are checked but not permanently reserved; a collision fails without retry.

## Terminal 2 — observation only

Once the Controller is waiting:

```bash
./lab.sh lab3 enter
```

Herdr opens **OpenShell**, then **Editor**. If the native splash appears, press a
key. Select the Controller's sandbox and open logs (`l`). The UI has its own
client identity, no trusted `/state`, preparation HOME or Docker socket.
Re-entry attaches eligible installed resources without task replay, reenrollment
or duplicate active apps. Partial/conflicting UI sessions are preserved and
refused; do not clear a tool HOME to force entry. Save unsaved Editor work before
STOP. UI arrangements may return to the starter layout; saved files, settings,
history and logs are not disposable layout state.

The Editor's [walkthrough](workspace/README.md) and policy/provider copies are
public reference snapshots, **not** enforcement/readiness receipts or live policy
editors. Read the filesystem/identity grants, exact helper destination/executable,
GET/preview-only HTTP rules and endpoint-bound provider configuration before START.
Do not put real keys in public configuration or display placeholder values.

## One task, useful Preview and native denial

Predict the outcome, then type **START once** in Terminal 1. Enrollment copies the
selected preparation key only inside a trusted temporary operator child, into
gateway provider storage. The workload receives a revision-scoped placeholder,
not the upstream key. Enrollment, model execution and revocation share a window
of at most five minutes; use of quota may cost. Time bounds are not monetary caps.

The agent prepares a menu using the preview skill/helper. That legacy helper also
attempts publication; this is not evidence of deliberate model disobedience.
On success, model access is removed before inspection. Refresh Preview/Live and
find the native event. Expected triggered outcome: useful updated Preview,
byte-unchanged Live, **DENIED POST `/publish`**, policy `conference_preview_only`,
engine `l7`. The intended Preview menu is **Filter Coffee** (hot) and **Jasmine
Iced Tea** (iced), both **฿75**, with new revision/build details. Live should retain
its original menu, revision and publication time. A stable-looking page, viewer
405, DNS error or tool prose is not OpenShell denial evidence.
A mixed allowed/denied publication tail is not accepted as successful
enforcement. Events can scroll out of the native UI; bounded private captures
remain available, but a full 1000-line tail is inconclusive: the Controller reports
native-event inspection failure, offers no CHECK and preserves the capture rather
than claiming that missing events prove no attempt. This matches the reference's
bounded attribution rule. Allowed network events alone do not prove model completion.

A successful non-trigger is valid. Only when offered, **CHECK** runs one explicitly
labelled **scripted boundary check, not agent behavior**; it may rebuild Preview.
No CHECK is offered after model/provider failure, timeout, changed Live or unusable
Preview. START and CHECK are consumed before dispatch, even if they fail. There is
no automatic model connectivity probe, task retry or task replay. Repair the
workflow or use a separately authorized release, rather than widen policy merely
to hide the denial. In this exercise, discuss that decision only: do not edit the
policy, publish or start another agent round.

## STOP and uncertainty

Save Editor work, detach Terminal 2 with **Ctrl+B**, release, then **q**, and type
**STOP** in the Controller. Detaching alone does not stop anything. Interrupts and
deadlines attempt STOP without waiting for detach. The total pipeline window is
30 minutes from activation, including a single two-minute cleanup reservation.
The watchdog is a host thread, independent of Pi/input but not controller death,
host suspension or an actual monetary guarantee.

After an interrupted Controller exits:

```bash
./lab.sh lab3 stop
```

STOP revalidates exact ownership, cuts supervisor/workload execution first,
stops operator workers before provider absence confirmation, then stops services.
A pending create/operator/enrollment fact is not discharged by an empty inventory.
A lost native create ACK never authorizes discovery/adoption of candidate IDs.
Uncertainty preserves evidence and the necessary gateway and blocks fresh attempts,
reset and removal. Do not change engines/state roots or delete control files to
bypass it. Inspect the recorded private phase/pending operation and full resource
identities on the original engine; do not share raw credentials or transcripts.
A live Controller owns its lifecycle lock: use its STOP/interrupt first.
There is intentionally no participant acknowledgement/recovery command that clears
uncertain facts. Repeating STOP may cut known owned execution without settling the
unknown operation. Such a failure can terminate Lab 3 use and block workshop
uninstall pending a separately agreed, evidence-based recovery procedure. Do not
edit the control JSON to manufacture settlement. The private control directory is
`${XDG_STATE_HOME}/secure-agent-workshop/lab3/`, or
`~/.local/state/secure-agent-workshop/lab3/` when unset. Read only `state.json`'s
`phase`, `pending`, `failure_stage` and `failure_kind` for the failed operation;
keep the full record/evidence private and preserve its original location/engine.

Local STOP/provider deletion does **not** revoke the upstream account key, erase
forensic evidence, roll back a changed site or cancel a request already accepted
by the cloud provider. If exposure is suspected, revoke the upstream key through
the provider's account/key settings separately.

## Repeat setup, configuration and another attempt

An existing selection must be verified stopped and settled before setup. Setup
never stops it implicitly. Differing managed gateway/editor files are listed for
one default-**No** whole-file replacement decision; declining blocks additions
as well. Matching and destination-only files, credentials, TLS, database, site
results, saved work, sessions, history and evidence remain. Multi-file publication
may be partial; there is no whole-deployment rollback. Tools interpret opaque
custom configuration; the workshop does not validate custom provider fields or
promise the default safeguards under arbitrary changes.

| Canonical source | Installed destination / consumer | Activation |
| --- | --- | --- |
| `config/openshell/gateway.toml.tmpl` | `/state/gateway.toml`, gateway bootstrap | Runtime identity/port/stock-image substitutions only; fresh activation |
| `config/openshell/policy.yaml.tmpl` | `/state/policy.yaml`, native sandbox create | Service-IP substitution; new sandbox/attempt |
| `config/openshell/provider.json` | `/state/provider.json`, native profile import | Import during activation, not credential enrollment |
| `../shared/config/herdr/config.toml` | operator `.config/herdr/config.toml`, Herdr | Next supported UI start |
| `../shared/config/fresh/config.json` and `config/fresh/init.ts` | operator `.config/fresh/`, Fresh | Next supported editor start; initializer is a lab override, not a merge |
| `config/pi/{models,settings}.json` | workload image `/http/`, launcher copies opaque bytes into its private profile | Rebuild plus separately consented recreation; **not** repeat setup deployment |

The two Pi files are image-installed. Existing environments retain their recorded
workload image and settings even if the mutable tag is rebuilt. Repeat setup must
not claim they were updated. Activation never uploads current checkout files.
Installed/read-back public files are distinct from native import, policy application,
provider readiness and active tool settings. Setup does not start services to
validate configuration or rearm consumed actions/deadlines.

For a deliberate new attempt, after verified STOP:

```bash
./lab.sh lab3 reset
./lab.sh lab3 run-pipeline
```

Reset shows exact scoped data loss and asks `(y/N)`. It preflights current public
software/inputs, rechecks stopped ownership/settlement, disposes only recorded
containers, networks, native channel/supervisor volumes, environment volumes and
private control/evidence, then creates a fresh **stopped** selection. No archive,
implicit STOP, native force-delete, provider enrollment or model task. Unknown
helpers/shared references block deletion. An uncertain deletion retains its pending
fact and remaining data; do not retry it as if nothing happened. Images,
preparation, other labs and unrelated data remain.

Workshop uninstall uses only:

```bash
./lab.sh remove
```

All labs must first be stopped and Lab 3 settlement verified. One default-No
confirmation covers validated workshop resources, local credentials and private
host state. Empty Docker inventory does not authorize discarding an unresolved
control record. Source/Git, personal configuration, host prerequisites, stock/shared
images and unattributed build cache remain. No global prune or upstream key
revocation. A partial failure is not successful removal.

## Selection and native acceptance gates

Control/evidence is one private `lab3/` under `${XDG_STATE_HOME}/secure-agent-workshop`,
or `~/.local/state/secure-agent-workshop` by default. It is never mounted into
operator/workload containers. No registry, active pointer, automatic resumption,
legacy migration or per-engine workaround is provided. Former custom state roots
are not discovered; changing roots is not recovery.

Before credential/provider testing, separately approve this **provider-free** stage
on each target engine architecture: `lab3 setup`, `lab3 run-pipeline`, open URLs,
`lab3 enter`, inspect native sandbox identity, detach, type STOP **without START**,
then `lab3 stop` to confirm stopped readback. No model quota/cost is intended in
that stage. Retain stopped resources and private evidence; deletion/reset requires
its own explicit scope and consent. A lost ACK, incomplete ownership or uncertain
STOP is an abort result, not permission for another attempt.

Later separately approved stages qualify START/enrollment/readiness/revocation,
trigger/non-trigger CHECK, re-entry, watchdog/controller death/late-effects,
changed/missing/declined configuration, preservation after source edits/rebuilds,
reset/repeat and root removal/fresh setup. The stock trusted supervisor still lacks
enforced CPU/memory/PID quotas. Synthetic HTML can spoof content, sequential site
writes are not atomic, and service case labels are unauthenticated selectors.
These are demo limitations, not production security guarantees.
