# Lab 2 · Run 2 — Build the agent's protection policy

This **Sandbox** card opens `/home/lab-user/policy`. Its `nono.json` controls
protected Pi, not the website or trusted Shell. Pi has not started yet; do not
run the Agent launch command until you finish the policy exercise.

For the full walkthrough, switch to **Lab 2 → README.md** in Editor and start
at **step 3 — Meet nono**. Steps 1–2 cover Run 1, not work to repeat in Run 2.

## What to do here

1. Meet nono, then follow step 4's **four Shell demos**: small sandbox, denied
   file read, blocked outbound request and inherited synthetic ENV.
2. Open `nono.json`; read the workshop-only hint in `meta.description`.
3. Try step 5's **three policy goals** before reviewing the answers:
   - **Reduce excessive file access** — remove `/home/lab-user/`; retain only
     required project/agent-state write grants and runtime read grants.
   - **`diagnostics.workshop.test`** — add the diagnostic destination to
     `network.deny_domain`.
   - **`WORKSHOP_PROTECT_ME`** — add the variable to `environment.deny_vars`.
4. Save with **Ctrl+S**. Confirm the HOME grant is gone before the profiled ENV
   check. Inspect nono's route and Pi's provider configuration read-only;
   preserve route `ollama_api_key`, ENV `OLLAMA_API_KEY` and port `18082`.
5. Follow step 6: reproduce the Coffee/Tea bug, then manually launch protected
   Pi in **Agent · tab 1** using the printed `nono run` command. Do not use plain
   `pi` or start a second supervisor. Entry checks are not policy-exercise checks.
6. Send the same debug-skill repair prompt. Review every changed/new file before
   trusted Shell tests/redeploy, then check independent orders in the browser.
   Inspect actual access, attempts, denials and any redacted receipts.
7. Follow step 7's bounded protected-Run-2 ENV/token demonstration and warnings.
8. **Exit Pi; keep the lab running.** In Shell, use step 8's native JSON audit
   list command. Match this run's closed session before inspecting it; keep
   JSON and broader metadata private. Missing records are inconclusive.
9. Compare the two runs, save work and follow step 9's host stop command.

The synthetic environment view is a new sandboxed child, not an extra Pi run.
Do not launch a second supervisor while protected Pi is already running.

## Read these sections

- `filesystem.allow`: directories where Pi may read and write.
- `filesystem.read`: installed tools and other read-only files.
- `environment.allow_vars`: inherited variables permitted initially.
- `environment.deny_vars`: inherited variables you exclude.
- `environment.set_vars`: values injected after filtering; keep these intact.
- `network.allow_domain`: workshop destinations permitted initially.
- `network.deny_domain`: destinations you exclude.
- `network.credentials`: credential routing through the nono supervisor.

The synthetic `WORKSHOP_PROTECT_ME` is inherited, not a `set_vars` entry.
The starter deliberately grants all of `/home/lab-user/` for the exercise.
Remove that grant while keeping the project and agent-state grants. This puts
support files, policy and supervisor state outside the narrowed grants.
Do not launch a profiled child or Pi before saving that reduction. Entry checks
do not verify that the exercise edits are complete. If already narrowed, keep
your policy narrow rather than restoring excessive access.

**Workshop only, not production best practice:** `*.workshop.test` is deliberately
broader than the repair needs, so you can add a network deny. Use **least
privilege** in real configurations: allow only required destinations (here the
app and separate provider route), files and inherited variables.
The real provider key remains outside Pi; Pi's session/phantom token is not that
key, but is still session authentication material. Do not print its value,
except the bounded protected-Run-2 demonstration in the Lab 2 guide, step 7.

Keep credential routing intact. After removing the whole-HOME starter grant,
do not add it back or grant the policy folder, key store or unrelated support
files to the child.
Do not paste an API key into this file.

If a tool is denied, decide whether it is necessary for the repair before
changing access. Do not widen permissions just to silence an error.

Policy edits apply to the next protected launch, not an already-running Pi.
Switching Fresh workspaces does not start Pi or apply the policy.

## Two kinds of tabs

**Lab 2 / Sandbox cards** switch folders inside Fresh.
**Ctrl+B**, release, then **1 / 2 / 3** switches the terminal tabs.
Copy with **Ctrl+C** in Fresh; paste into Shell using your host terminal’s
Paste command (**Cmd+V** on macOS). **Ctrl+V** is for pasting inside Fresh.
