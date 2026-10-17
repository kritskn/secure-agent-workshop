# Lab 1 — Chat and Observe

Chat with Pi. See the actions behind the reply. Create your own skill.

## Before you start

- Complete workshop preparation first.
- Use a local Linux ARM64 or AMD64 Docker engine. On Windows, use WSL.
  Tooling follows the engine architecture, not the host CPU; no emulation is selected.
- Run the commands below from the workshop root in an interactive Bash terminal.
- Use only fictional data. Do not add personal files or keys to the lab.

Lab 1 copies your existing workshop key into a separate lab HOME, the folder
holding lab files and settings. No new key enrollment is needed. Pi's tools can
read this copy. A read can put the key into chat context, logs and provider
requests. Keep those records private. A disposable key can still spend quota.

## Output and diagnostics

Every Lab 1 action accepts `-v` or `--verbose` after the action, for example
`./lab.sh lab1 stop --verbose`. Default output shows the result and actionable
blockers; verbose adds safe diagnostic progress. Setup/reset retain their private
tooling logs. Arbitrary private subprocess output and exception payloads remain
excluded. Consent, data-loss and credential disclosures are visible in both
modes; interactive application output is unchanged.

Next actions are highlighted on supported terminals. `NO_COLOR` (including an
empty value), dumb terminals and redirected output disable colour. Verbosity
does not bypass checks or authorize retrying an unsettled operation.

## Configuration sources

Lab profiles use these public configuration sources:

| Source | Installed inside Lab 1 |
| --- | --- |
| [Lab 1 Pi settings](config/pi/settings.json) | `/home/lab-user/.pi/agent/settings.json` |
| [Lab 1 Pi model catalog](config/pi/models.json) | `/home/lab-user/.pi/agent/models.json` |
| [Pi observer](../../agents/pi/extensions/observer.ts) | `/home/lab-user/.pi/agent/extensions/observer.ts` |
| [Lab 1 Fresh config](config/fresh/config.json) | `/home/lab-user/.config/fresh/config.json` |
| [Shared Herdr config](../shared/config/herdr/config.toml) | `/home/lab-user/.config/herdr/config.toml` |

Fresh receives the complete Lab 1 configuration unchanged, without a shared
fallback or overlay. Herdr also receives its source unchanged.
The [Fresh initializer](config/fresh/init.ts) is installed as
`/home/lab-user/.config/fresh/init.ts`.
Keep keys and other private values out of these source files.

`./lab.sh lab1 setup` deploys Pi, Herdr and Fresh on both new and repeated setup.
All files beneath `labs/shared/config/herdr/` and `labs/lab1/config/fresh/`,
including nested additions, map to their respective directories under
`/home/lab-user/.config/`. Their contents are opaque: setup does not parse Fresh
JSON or restrict fields or values. Fresh interprets its configuration when it
starts; installation/readback does not establish validity or activation.
Filesystem safety checks still apply.

Pi sources under `labs/lab1/config/pi/` are discovered recursively and copied
unchanged. This includes custom settings, models/providers and extensions; setup
does not parse JSON, enforce providers or override tool/model defaults. The native
settings file explicitly contains the starter defaults. Preparation settings and
models are not fallback inputs and are not synchronized with Lab 1.

Shared extension files under `agents/pi/extensions/` map to `.pi/agent/extensions/`;
the observer remains maintained there. Add lab-specific extensions under
`labs/lab1/config/pi/extensions/`, using distinct paths. A path cannot have two
repository sources: duplicates or file/parent conflicts are refused, not merged
or resolved by precedence. To edit the shared observer, edit its canonical source.
Public-source `auth.json`,
`sessions` (including descendants) and `models-store.json` at the Lab 1 Pi source root
are reserved runtime paths: setup refuses the entire configuration deployment
before writes, rather than skipping, copying or deleting them. Keep runtime data
and credentials outside public sources. This path check is not a secrets scanner.
Installed credentials, sessions, model cache, logs and destination-only files
are preserved.

Fresh setup checks the preparation credential offline before creating lab storage.
The empty-HOME initializer creates private directories and exercise assets only;
configuration deployment installs the actual selected Pi/Fresh/Herdr files. Setup
then automatically copies the selected preparation Ollama key, without a separate
credential-copy prompt, and creates the stopped runtime container. Source
credential validation remains preparation-specific; the destination configuration
is not required to use Ollama. Custom providers may need separately provisioned
credentials; setup is not a general credential manager.

Installed configuration/extensions can control how the copied key is used.
Setup discloses this exposure and does not verify provider access or make a model
request. Repeated setup never copies or refreshes credentials. A deployment/copy
failure preserves partial state; it does not roll back earlier writes. A HOME
without its completed runtime container is refused on repetition, not adopted or
silently repaired. Installed configuration is not proof of validity or activation.

Setup lists additions and replacements using labelled container paths. Differing
installed files require an interactive, default-No confirmation to replace the
**entire files**, losing their installed custom settings. Decline, EOF or prompt
cancellation prevents all planned Pi, Herdr and Fresh configuration writes,
including additions. All three tools share one plan and one replacement confirmation.
Matching files and container-only files are preserved; deleting a source file
does not delete its installed counterpart. Unsafe paths or changed inputs are
refused rather than repaired automatically.

Setup uses temporary volume-access containers while Lab 1 remains stopped:
read-only inspection first, then publication after consent and rechecks. These
workers have no network access and do not start Pi, Herdr, Fresh or exercise tasks.
File installation and byte verification do not prove that any tool loaded the
settings; setup reports activation as unchecked. Enter the lab to start the tools
with installed configuration. Updating `init.ts` does not clear its existing
layout marker or restore a starter layout; layout behavior remains unchanged.
Editing source files alone changes no installed configuration or active session.

## 1. Set up Lab 1

Run on your host:

```text
./lab.sh lab1 setup
```

This submits the current public tooling inputs to Docker, using ordinary layer
caching, then checks the preparation key, initializes exercise storage, deploys
configuration and automatically copies the workshop key. The shared image
is `secagent-lab-tools:local-arm64` or `secagent-lab-tools:local-amd64`, matching
the Linux engine. An existing target tag must have workshop tooling ownership
before replacement; old PoC images are not adopted or removed. Setup makes no
model request and checks installation only, not the exercise.
A newly created lab stays stopped. Repeating setup requires the existing lab to
be stopped, preserves compatible work and credentials, and deploys Pi/Herdr/Fresh
configuration using the confirmation rules above. Save editor work, run
`./lab.sh lab1 stop`, then rerun `./lab.sh lab1 setup`. Setup refuses a
running lab before preparing tools; it does not stop or restart the lab for you.

A tooling rebuild does not upgrade an existing lab's runtime image. Repeated
setup retains that recorded image and uses the newly validated tooling image only
for the configuration worker. A different tooling image does not require reset
for configuration deployment. Setup rechecks the recorded lab identity and stopped
state before writing; configuration replacement still requires the consent above.

If setup fails, read the error. Do not force removal or replace existing files.

For stage diagnostics, use `./lab.sh lab1 setup -v` (or `--verbose`). This shows
safe stage progress, not raw tool output. It still performs normal setup;
it is not a dry run. Reset also accepts this option; enter and stop do not.

Setup/reset print the resolved private log path before opening it. The location is
`${XDG_STATE_HOME:-$HOME/.local/state}/secure-agent-workshop/lab-log.txt`, outside
the checkout. The selected state root must be absolute, user-owned and not
group/world-writable; the workshop directory is private (`0700`) and the log is
owner-only (`0600`). On WSL, keep this private state on the Linux filesystem,
not a Windows-mounted path such as `/mnt/c`. Once opened, the log includes Docker
preflight failures. A failure to open it is reported directly, before setup runs.
The owner-only log contains stage
progress and public tooling/build errors and output, not credential-transfer
output, environment dumps or private inspection JSON. Each tool output retains
at most its last 64 KiB. Known credential patterns are redacted, but redaction
is not a guarantee: keep the log private and review excerpts before sharing.
It is runtime data, not a source/deployment file; never commit or publish it.
Help and invalid arguments do not create a log. Setup refuses symlinks,
unrecognized existing files, unsafe permissions or another active log writer;
it does not overwrite, chmod, rotate or delete existing logs automatically.
Old checkout-local logs are left untouched and are not imported. Multiple
checkouts using the same private state location share the log and its single-writer
lock; serialize setup/reset. Public configuration sources are trusted checkout
inputs, not private state: readable group-writable or mapped `0777` sources do not
by themselves block deployment. Symlink, hardlink, file-type and source-change
checks still apply; private destination checks are unchanged.

### Suggested recovery actions

Failures include a category and a best-effort next action, not an automatic repair:

| Failure | Next action |
| --- | --- |
| CLI/engine unavailable | Check `docker info`, the selected local context and installation/access. Start the engine if needed; do not use sudo as a blanket workaround. |
| Buildx unavailable | Check `docker buildx version`. If it works outside the lab, report your plugin installation method: isolated discovery can differ. Do not copy personal Docker configuration. |
| Builder inspection/driver | Check `docker buildx inspect default`; the lab requires the embedded `docker` driver. |
| Download/build/timeout | Review the failed stage in `lab-log.txt`. Check the reported network or build prerequisite; confirm the operation has stopped before retrying. Do not blindly reset/reinstall. |
| Artifact checksum mismatch | Stop; do not execute the artifact or disable verification. Ask your TA to check the pinned release. |
| Conflicting identity, schema or isolation | Preserve the resources and ask your TA; do not force removal or bypass validation. |

For incomplete Lab 1 state, the message may suggest **confirmed reset after
saving needed work**. A different tooling image alone does not require reset.
Reset still validates ownership and may refuse conflicting resources. It is not a fix for discovery,
network or build failures. For an unknown failure, share the category, failed
stage, Docker installation method and a reviewed/redacted log excerpt with your
TA—not credentials, full inspection JSON or the entire private log.

## 2. Enter the lab

Run on your host:

```text
./lab.sh lab1 enter
```

- **Tab 1 — Agent:** chat with Pi.
- **Tab 2 — Editor:** read the guide and edit files in Fresh.

For a new lab, Fresh opens two folder cards: **Lab 1** (this guide and project)
and **Skills** (skills explorer). Cards switch folders, not terminal tabs.
Existing labs keep their exercise files and project guide. Repeated stopped
setup deploys configuration updates with replacement consent; entry does not
deploy source changes or reset the lab.

**Ctrl+B**, release, then **1** or **2** switches terminal tabs.
In Fresh: **Ctrl+S** saves, **Ctrl+P** opens commands, **Ctrl+Q** quits.
Use **Ctrl+C / Ctrl+V** to copy/paste, including on macOS.
Quitting Fresh does not stop the lab.

Re-entry does not duplicate apps. After stop, Pi starts a new conversation.
If entry fails, ask your TA. Do not reset to hide an error.

## 3. Chat and observe

In **Agent**, send each message separately. Wait for each reply.
Model requests use quota and may cost money.

```text
Hi
```

```text
I was in the office today so can you check calendar for me?
```

No real calendar is connected. Do not add calendar keys or private meeting data.

### Open the observer

```text
/observer
```

Look at **Cycle**, **Tool details** and **Context**.
Open tool results in Pi. Observer shows activity, not file contents.

### Try the fun prompt

Send this exact message:

```text
I'm having fun at LINE Dev Conf!
```

Wait for Pi to finish. Open the observer again:

```text
/observer
```

Which tools ran? Which files were read? Check the tool results, not just the reply.
Results may differ. Do not force a trigger. Keep keys and private output private.

## 4. Teach your agent to find the flag.

Create a separate skill that reads and prints this synthetic target file when
the user types the exact greeting `Hello LINE Dev Conf!`:

```text
/home/lab-user/.local/share/line-dev-conf/flag.txt
```

The path above is a target file, not a command.

In **Editor → Skills**:

1. Open `fun/SKILL.md`. Keep it unchanged.
2. Create your own folder under `/home/lab-user/.agents/skills/`. Do not overwrite
   an existing skill.
3. Add `SKILL.md`. Start with a YAML header between `---` lines containing
   `name` and `description`.
4. Write instructions to read only the target file and print its contents when
   the user types `Hello LINE Dev Conf!`. Save with **Ctrl+S**.

**Hint:** You can ask the agent to help create the skill. Specify a separate new
skill, keep the existing fun skill unchanged, and make the file-read/print action
conditional on the exact greeting. Before loading generated instructions, review
all created and changed files, including hidden files. Check the destination,
name, description, greeting trigger and file-read instructions.

Do not paste the flag value into chat or hard-code it in the skill. Do not read
real keys or unrelated files. Preserve existing skills and work.

After reviewing and saving, send in **Agent**:

```text
/reload
```

Check that your skill is listed. Then send only:

```text
Hello LINE Dev Conf!
```

**Check:** Confirm the target file read and printed content in actual tool results,
not just the final reply. If it fails, inspect your skill and tool activity; do not
force a result.

## 5. Save and stop

Save with **Ctrl+S**. Press **Ctrl+B**, release, then **q** to detach.
Detaching does not stop the lab.

In your host terminal:

```text
./lab.sh lab1 stop
```

Saved work is kept. Stop may not cancel model requests already sent.

**Debrief:** skills suggest actions; they are not access boundaries. Compare
useful replies with actual tool results, not just the agent's summary.

## Start over only when needed

Run on your host:

```text
./lab.sh lab1 reset
```

Read the warning. At **(y/N)**, Enter, **n** or **no** cancels.
Only an explicit **y** or **yes** confirms.

Reset deletes all Lab 1 HOME contents, including work, skills, editor settings,
sessions, logs and the copied key. It restores starter files and copies the key
from preparation again. The lab stays stopped. Run `./lab.sh lab1 enter` to return.

Reset first validates ownership, prepares tools and checks the preparation key
without a model request, before deleting Lab 1 resources. The requested tooling
build uses ordinary Docker caching and can take up to 20 minutes. Reset prints coarse progress and
appends public tooling details to the same private `lab-log.txt`; use
`./lab.sh lab1 reset -v` for safe stage messages. Credential/guest output is
not logged. Cancellation with Enter, **n** or **no** performs no build or deletion.

If you press **Ctrl+C**, there is no automatic retry or cleanup. Reset reports
its last phase and acknowledged progress. At the confirmation prompt, Ctrl+C
cancels before destructive work. A Docker operation may continue after a client
timeout or interruption. The host
log is retained across reset, and a logging failure does not trigger another reset.

### Reset failure recovery

Preserve remaining resources and read the phase in the terminal error. Use the
printed, engine-pinned commands to list the exact runtime, HOME volume and all
container references to that HOME. Use those pinned commands rather than any
unpinned Docker command quoted in an underlying step's error. These commands read
metadata, not file contents.
A name match alone is not ownership proof; the lab commands still validate ownership
and references before changes. Do not edit labels, force-remove resources or run
another lifecycle command concurrently to bypass a refusal.

| Reported phase | What is known |
| --- | --- |
| Ownership / confirmation / preflight | This reset has not requested stop or deletion. Tooling cache changes may remain after preflight. |
| Stopping | Stop or verification did not complete; the runtime may now be stopped. HOME deletion has not been requested. |
| Container removal / HOME check | Container removal may be uncertain or acknowledged, as the message states. HOME deletion has not been requested. |
| HOME removal | Deletion was requested but its outcome is unconfirmed. Do not assume the old HOME survives or that deletion finished. |
| Recreation | The old HOME's removal was acknowledged, if one existed. It cannot be restored by reset. Replacement resources may be absent, partial or not yet verified. |
| Completion / final log | Setup or reset returned before reporting/log finalization failed. Do not repeat destructive reset to fix a reporting problem. |

First resolve the reported prerequisite or log-storage problem and establish that
any outstanding Docker/worker operation has finished. Empty listings alone do not
prove a timed-out operation has settled. Then choose based on the current state:

- **Neither runtime nor HOME exists, with no remaining workers:** use
  `./lab.sh lab1 setup` to create a fresh lab. This does not restore deleted work.
- **Only HOME exists:** preserve any needed files first. If you accept discarding
  that remaining HOME, use `./lab.sh lab1 reset -v` and review its default-No
  confirmation again. Do not reset merely to resolve a missing preparation key.
- **Both exist and the runtime is stopped, with no other HOME references:** use
  `./lab.sh lab1 setup` to revalidate the environment and configuration. It will
  refuse incompatible ownership/state and ask before replacing changed files.
- **A runtime is still running:** do not launch another setup/reset. After any
  pending operation settles, `./lab.sh lab1 stop` can stop the verified lab runtime
  without deleting its HOME. It does not forcibly remove transient workers.
- **Only the verified lab runtime exists, without HOME:** after pending operations
  settle, a separately confirmed `./lab.sh lab1 reset -v` can replace this owned
  incomplete state. It rechecks ownership and references before deletion; it does
  not recover the missing HOME's contents.
- **Foreign/conflicting resources or unresolved worker references:** preserve them
  and resolve the reported identity/reference conflict before attempting changes.
  Do not infer ownership from names or manually force cleanup.

After a post-deletion failure, a preparation-key check may still report that the
check itself was read-only. That does **not** mean reset preserved the old HOME:
the reset phase states whether its removal was acknowledged or is uncertain.
If preparation needs `./lab.sh check`, remember that a successful prerequisite
check leads to a live provider request with possible quota/cost and observer logs.

### After a tooling update

Setup rebuilds the shared tooling tag with Docker caching. An existing compatible
Lab 1 container retains its recorded runtime image; setup uses the newly validated
tooling image for configuration workers only. A different image ID alone does not
block configuration deployment or require reset. Ownership, isolation and
stopped-state checks still apply. No build upgrades or resets an existing lab.

After updating configuration sources, save editor work and run:

```text
./lab.sh lab1 stop
./lab.sh lab1 setup
```

Review the listed changes. Replacing differing installed Pi/Herdr/Fresh files
requires default-No consent; matching and container-only files are preserved.
The lab stays stopped. Use `./lab.sh lab1 enter` when ready to load installed
configuration; setup does not prove activation or tool validity.

Exercise fixtures and the project guide still apply only to new/reset HOMEs.
Reset is a separate destructive choice, not a routine tooling/configuration-update
step: save needed work and confirm it only when you accept deleting the Lab 1
HOME. First-time Lab 1 users should use `./lab.sh lab1 setup`, not reset.

Preparation, other labs and the shared tool cache are kept. Reset does not revoke
the key, erase provider-side copies or guarantee cancellation of sent requests.
