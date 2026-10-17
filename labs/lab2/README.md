# Lab 2 — Fix the app. Limit the agent.

Prepare the Coffee/Tea repair exercise twice: broad agent access in Run 1, then
configured protection in Run 2. Useful work and actual access will be compared.

**Setup, entry, stop and reset candidate for AMD64 or ARM64 Linux Docker.** Setup
prepares the selected run and leaves its services stopped. Reset recreates one stopped
run after explicit consent. Neither command launches Pi, submits a task or makes
a model request; installed files are not proof of active configuration or sandbox
enforcement. Automated checks and independent review passed for the source
candidate, including reset. Combined hands-on acceptance remains pending.

## Before setup

Complete [workshop preparation](../../README.md) first. Use Bash, Python 3.9 or
newer and the same selected local Linux Docker engine throughout. On Windows,
use WSL2 Bash with Linux Docker. Setup never starts Docker or changes its context.

Use one lab at a time, without overlapping lifecycle commands. Do not run
preparation setup/check/removal or image mutations during a lab transition.
This is a usage requirement, not automatic cross-command exclusion.

## Output and diagnostics

All Lab 2 actions accept `-v` or `--verbose` after the action, before or after
its run options. For example: `./lab.sh lab2 setup --run 1 --verbose`.
Default output is concise; verbose adds authored stage details and full scoped
failure-inspection guidance. Credentials, private subprocess output and raw
exception payloads remain excluded. Interactive application output is unchanged.

Consent scope, data-loss warnings, partial-state/uncertainty blockers and
credential-exposure disclosures remain visible in both modes. Colour is used
only on supported terminals; `NO_COLOR` (including an empty value) disables it.
Verbose changes output only: it does not bypass checks, perform recovery or make
an uncertain operation safe to retry. Do not rerun a lifecycle command merely to
get verbose output while an earlier operation is unsettled.

## Prepare the two runs

Start with Run 1 from the workshop repository on your host:

```sh
./lab.sh lab2 setup --run 1
```

Set up Run 2 after saving and stopping Run 1, following the transition below.
Each run has separate owned storage and stopped containers. Setup prepares shared
tooling using normal Docker caching, then composes the Lab 2 software from
validated local tooling and nono images. Shared tooling builds may download public
software, including `curl` for the blocked-network Shell demo; Lab 2 composition
itself disables build networking. Builds do not upgrade existing run containers
or recreate environments automatically. An existing run does not gain `curl`
just because the tooling image was rebuilt; preserve work and arrange any
recreation separately rather than silently resetting it.

Fresh setup checks the selected preparation credential offline before creating
lab storage, then copies it automatically without a separate key-copy prompt.
Run 1's broad-access launcher exposes the key to its agent. Run 2's default policy
uses a supervisor/proxy instead of passing the real key to the protected child.
Its starter intentionally grants the whole lab HOME for the exercise. Remove
`/home/lab-user/` before any profiled child or Pi launch; until then, support,
policy and supervisor state are inside the writable grants. The real-key file
remains outside HOME. Entry checks metadata/routing, not the completed policy
edits. Configuration edits can change exposure. No provider verification or containment
qualification occurs here. Keep keys and private values out of public source.

The reserved browser ports default to **18080** for Run 1 and **18081** for Run 2,
on loopback only. No browser service is started by setup. To select another port:

```sh
./lab.sh lab2 setup --run 1 --app-port 19080
```

Ports must be decimal integers from 1024 through 65535. Repeat setup retains the
installed port when `--app-port` is omitted; a conflicting explicit value is
refused, not silently changed.

## Enter and stop

Use an interactive terminal, and enter only one run at a time:

```sh
./lab.sh lab2 enter --run 1
# Save work; Ctrl+B then q detaches, but does not stop services.
./lab.sh lab2 stop --run 1
./lab.sh lab2 setup --run 2
./lab.sh lab2 enter --run 2
# Save work and detach before stopping this run.
./lab.sh lab2 stop --run 2
```

Entry checks recorded resource identities, starts existing services, checks
readiness, and opens the Agent / Editor / Shell layout. It does not build images,
deploy configuration, refresh credentials or submit a model prompt. Run 1 opens
Pi with its intentionally broad access. Run 2 validates the installed protected
launcher and shows its **manual launch command** in the Agent tab; it does not
automatically start protected Pi, controls or a model task. Follow the installed
exercise instructions. Model usage you initiate uses quota and may cost.

Open the printed loopback browser address on the Docker host (default
`http://127.0.0.1:18080` or `http://127.0.0.1:18081`). The browser is not launched
automatically. Re-entry preserves saved work, configuration, credentials,
histories and logs; it must not duplicate active applications or replay prompts.
Starter layouts may be restored. Save unsaved editor buffers before re-entry or
stop. Stop closes the matching UI and stops owned containers, keeping storage.
It does not revoke provider credentials or prove cancellation of an in-flight
model request. Detaching alone leaves services and tasks running.

On a failure, retain partial state and inspect the reported selected-run
resource/status. Do not force-stop, reset, delete reservations or blindly retry
an operation whose outcome is uncertain.

## Follow the presentation exercise

Open **Editor → Lab 2 → README.md** manually in Explorer. The installed
[participant guide](poc/instructions.md) follows this sequence:

1. **Run 1:** reproduce the shared-order bug, use the installed debug skill,
   review every changed/new/hidden file, then test, redeploy and inspect access.
2. Save and stop Run 1; set up and enter the separate Run 2. Do not undo repairs.
3. Before starting protected Pi, try four Shell demos: greeting, file read
   outside/inside nono, blocked `curl` request and synthetic ENV inheritance.
4. In **Sandbox → nono.json**, try the three policy goals, then review the
   answers in order: files, network and ENV. The installed starter includes
   `/home/lab-user/` for participants to remove. Save the narrowed grants before
   the profiled ENV check or Pi launch. Preserve required runtime grants and
   credential routing. Inspect the provider route read-only.
5. Reproduce the bug, manually launch protected Pi, and send the same repair
   prompt. Review changes before trusted Shell tests/redeploy. Compare actual
   access, then follow the bounded protected-token check and closed-session audit.
6. Save, detach and stop the selected run. Refusal/non-triggering is valid;
   repair success or missing receipts is not proof of complete containment.

Guides are seeded into new runs, not rewritten by repeated setup or entry.
Read updated source guides here for an existing run; do not reset just to update
instructions. Replacing an already-narrowed policy with the broad starter on
repeated stopped Run 2 setup requires the existing whole-file replacement
confirmation; it is not silently restored. Preserve narrowed policies unless
deliberately starting the exercise again. Commands that invoke Pi/models use quota and may cost money.

## Reset one stopped run

**Destructive; providing these commands does not authorize native deletion.** Save
any work/evidence you want to retain outside the selected run, without placing
credentials or private data in the source checkout. First save editor work,
detach and confirm stop, then use an interactive terminal:

```sh
./lab.sh lab2 stop --run 1
./lab.sh lab2 reset --run 1
# For Run 2, use --run 2 in both commands instead.
```

Reset requires a complete, verified stopped run. It lists exact resources and
asks once, default **No**; only `y`/`yes` confirms. Enter/no/EOF/Ctrl-C at the prompt
leaves the run intact. Before deletion it prepares current public images and
checks public inputs and the preparation key offline; downloads may occur, but
no provider/model request is made. A preflight failure deletes no participant data.

Confirmation authorizes deleting only the selected run's containers, networks and
five volumes: saved project edits, agent HOME/configuration, credentials,
histories/logs, orders and receipts. **No archive or rollback.** Reset retains the
installed browser port, seeds current starter/configuration inputs, automatically
copies the selected preparation credential and leaves the fresh run stopped.
Run 1 exposes that key to its broad-access agent. Run 2 restores the excessive
whole-HOME starter grant and supervisor/proxy credential routing; repeat the
policy exercise before any profiled launch. The other run, preparation, Lab 1,
images/cache, host
diagnostic logs, source and unrelated resources remain. Reset does not revoke
provider credentials, undo prior exposure or cancel already-submitted requests.

Ownership, identity, stopped state and references are checked again before each
deletion. Missing old images do not require adopting or starting old resources.
Incomplete/conflicting resources or existing workers/reservations are refused;
reset is not partial-state recovery. Failures after deletion begins can leave
partial old storage or an incomplete replacement and a blocking reservation.
Preserve those resources and the printed progress; do not retry setup/reset,
force-delete a reservation or assume an outstanding Docker operation settled.
Use the selected engine to inspect the reported container status and the bounded
metadata commands printed on failure before agreeing a scoped recovery. There is no
automatic rollback, retry or cleanup of uncertain outcomes.

## Configuration sources

Setup deploys these canonical public inputs. It does not merge configuration
files or require workshop-specific field values; the tools interpret their
configuration. Only the initializer's selected-run token and policy's public run
identity token are rendered.

| Source | Installed inside the selected run, below `/home/lab-user/` |
| --- | --- |
| [Lab 2 Fresh config](config/fresh/config.json) | `.config/fresh/config.json` |
| [Fresh initializer](poc/fresh-init.js) | `.config/fresh/init.ts` |
| [Shared Herdr config](../shared/config/herdr/config.toml) | `.config/herdr/config.toml` |
| [Pi settings](config/pi/settings.json) | `agent-state/.pi/agent/settings.json` |
| [Run 1 models](config/pi/run1/models.json) / [Run 2 models](config/pi/run2/models.json) | `agent-state/.pi/agent/models.json` |
| [Shared observer](../../agents/pi/extensions/observer.ts) | `agent-state/.pi/agent/extensions/observer.ts` |
| [Run 2 nono policy](config/nono/policy.json) | `policy/nono.json` (Run 2 only) |

Repeat setup requires **every container in the selected run to be stopped**.
It lists differing managed paths and asks once, default **No**, before whole-file
replacement. Decline, EOF or cancellation blocks the whole configuration batch,
including additions; it does not report successful deployment. Matching and
destination-only files, credentials, sessions and saved project work are preserved.
Repeat setup neither refreshes keys nor changes the other run. Running,
incompatible or incomplete state is refused without automatic stopping or repair.

Editing source alone does not update an installed run. Repeat the matching setup
command to deploy configuration when the run is confirmed stopped. Successful
read-back establishes installation, not that a running tool loaded the files.
Image-installed code and teaching assets in existing containers are not upgraded
by repeat setup; any recreation needs a separately agreed destructive operation,
not an implicit reset.

## Logs and incomplete setup

Setup prints its private log path, outside the checkout, normally
`${XDG_STATE_HOME:-$HOME/.local/state}/secure-agent-workshop/lab-log.txt`.
Existing unsafe private state is refused, not chmodded, migrated or bypassed.

On failure, preserve the reported resources and follow the printed bounded
metadata-inspection guidance. Unknown or unconfirmed outcomes may leave partial
resources and a setup reservation; sequential use does not settle outstanding
Docker operations. Do not force-delete the reservation, adopt partial state,
blindly retry, change permissions or reset preparation as a workaround.

Root `./lab.sh remove` is a destructive workshop
uninstall, not a recovery procedure or removal of preparation only. After all
labs are stopped, it lists verified preparation/Lab 1/Lab 2 resources, owned
cached/retention images and safe workshop host-state directories, then asks once,
default **No**. Confirmation deletes listed credentials, projects, configuration,
orders, receipts, histories and logs. Source and personal configuration remain;
shared/unattributed build cache is not pruned. Unknown ownership, unrelated
references, setup reservations and unintegrated Lab 3 resources block removal.
Partial failure is reported, not rolled back or described as success.

Native execution and deletion require separately agreed acceptance steps; the
source candidate is not yet hands-on accepted. See `./lab.sh lab2 --help` and
`./lab.sh remove --help` for supported command summaries.
