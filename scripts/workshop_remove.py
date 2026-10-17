"""Consented lab-specific STOP and removal of verified workshop resources.

Names select candidates; ownership and consented identities authorize effects.
No force, prune, rebuild, uncertain-operation recovery or legacy adoption.
"""

import argparse
import json
import os
import re
import shlex
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab1_runtime
import lab1_setup
import lab2_entry
import lab2_resources
import lab2_setup
import lab2_state
import lab3_dispose
import lab3_pipeline
import lab_credential
import lab_tools
from lab_log import next_action, progress

OWNER = lab_tools.OWNER
PREPARATION = {"init": "preparation-initializer", "auth": "preparation-enrollment",
               "check": "preparation-check"}
IMAGE_ROLES = {"runtime": "preparation-runtime", "nono": "preparation-nono",
               "openshell": "preparation-openshell", "lab-tools": "lab-tools", "lab2": "lab2-software",
               "lab3-site": "lab3-site", "lab3-workload": "lab3-workload",
               "lab3-gateway": "lab3-gateway", "lab3-ui": "lab3-ui"}


class Refused(RuntimeError):
    """Authored removal diagnostics; never format private Docker payloads."""


def inspect(docker, kind, name):
    rows = json.loads(docker.run([kind, "inspect", name]))
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise Refused(f"Cannot confirm {kind} {name!r}; preserve it and inspect its identity.")
    return rows[0]


def labels(item, kind):
    return ((item.get("Config") or {}).get("Labels") if kind in ("image", "container")
            else item.get("Labels")) or {}


def identity(item, kind):
    value = item.get("CreatedAt") if kind == "volume" else item.get("Id")
    pattern = r"sha256:[0-9a-f]{64}" if kind == "image" else r"[0-9a-f]{64}"
    if not isinstance(value, str) or not value or (kind != "volume" and not re.fullmatch(pattern, value)):
        raise Refused("Resource identity unavailable; nothing further removed.")
    return value


def validate_resource(item, kind, name, *, lab3=None, for_stop=False):
    """Check preparation owner/role and current lab schemas, including detached storage."""
    if lab3 is not None and name in lab3.get(kind, {}):
        if lab_tools.removal_identity(item, kind) != lab_tools.removal_identity(lab3[kind][name], kind):
            raise Refused("Recorded Lab 3 identity changed; preserve it and review STOP settlement.")
        return
    tags = labels(item, kind)
    if tags.get("org.secagent.owner") != OWNER:
        raise Refused(f"Ownership of {name!r} is unconfirmed; preserve it. Names alone do not authorize removal.")
    role = tags.get("org.secagent.role")
    if kind == "container":
        try:
            if for_stop and resource_group(name) in ("lab1", "lab2-run1", "lab2-run2"):
                lab2_state.lifecycle_state(item, name)
            else:
                lab2_state.stopped(item, name)
        except lab2_state.Refused:
            if for_stop and resource_group(name) in ("lab1", "lab2-run1", "lab2-run2"):
                raise Refused(f"Removal blocked: container {name!r} has uncertain lifecycle state. "
                              "\n[NEXT] Inspect its status on the selected engine with docker container ls --all; "
                              "no automatic STOP or deletion. Only review ./lab.sh remove again after the outcome is settled.") from None
            if name == lab1_setup.CONTAINER:
                next_step = "Save work, then use ./lab.sh lab1 stop and confirm it completed."
            elif match := re.fullmatch(r"secagent-lab2-run([12])-(agent|app|collector|gateway)", name):
                next_step = f"Save work, then use ./lab.sh lab2 stop --run {match[1]} and confirm it completed."
            else:
                next_step = "Inspect this container's status; let its operation finish or diagnose it without forcing a stop."
            raise Refused(f"Removal blocked: container {name!r} is not confirmed stopped. "
                          f"\n[NEXT] {next_step}\nOnly review ./lab.sh remove again after the outcome is settled; "
                          "no implicit stop or deletion.") from None
    if name == "secagent-vol" and kind == "volume":
        lab_credential.validate_volume(item, name, "preparation-home")
    elif name == lab1_setup.VOLUME and kind == "volume":
        lab_credential.validate_volume(item, name, "lab1-home")
        if not re.fullmatch(r"[0-9a-f]{32}", tags.get("org.secagent.run-id", "")):
            raise Refused("Lab 1 volume generation is unknown; preserve it.")
    elif name == lab1_setup.CONTAINER and kind == "container":
        generation = tags.get("org.secagent.run-id", "")
        if not re.fullmatch(r"[0-9a-f]{32}", generation):
            raise Refused("Lab 1 container generation is unknown; preserve it.")
        lab1_setup.validate_runtime(item, item.get("Image"), generation)
    elif name in {"secagent-prep-" + suffix for suffix in PREPARATION} and kind == "container":
        if role != PREPARATION[name.removeprefix("secagent-prep-")]:
            raise Refused("Preparation container role differs; preserve it.")
    elif match := re.fullmatch(r"secagent-lab2-run([12])-(.+)", name):
        run, part = int(match[1]), match[2]
        if lab2_resources.Plan.roles().get(part) != kind:
            raise Refused(f"Unresolved Lab 2 worker/reservation {name!r}; finish or diagnose its operation first.")
        plan = lab2_resources.Plan(run, tags.get("org.secagent.run-id", ""),
                                  item.get("Image", "sha256:" + "0" * 64),
                                  int(tags.get("org.secagent.lab2.app-port", "0")))
        plan.validate(item, part)
    else:
        command = ("docker --host '<selected-unix-endpoint>' " + kind
                   + " inspect --format '{{.Name}}' " + shlex.quote(name))
        raise Refused(f"No qualified cleanup for {kind} {name!r}; deletion of this resource is not authorized. "
                      f"List its name without private contents using: {command} "
                      "(replace <selected-unix-endpoint> with the endpoint used for this operation). "
                      "Preserve it; Lab 3/provider and unknown probe cleanup are not inferred from labels.")
    identity(item, kind)


def host_inventory(home, selected_state, *, lab3_paths=()):
    """Inspect exact workshop state roots without creating or reading files."""
    roots = {home / ".local/state/secure-agent-workshop"}
    if selected_state:
        roots.add(Path(selected_state) / "secure-agent-workshop")
    protected = {root / "lab3" for root in roots}
    result = {}
    roots = {root for root in roots if not any(parent in roots for parent in root.parents)}
    for root in sorted(roots):
        if not root.is_absolute() or ".." in root.parts:
            raise Refused("Host state path must be absolute without '..'; nothing removed.")
        for parent in (*root.parents, root):
            if os.path.lexists(parent):
                info = parent.lstat()
                if not stat.S_ISDIR(info.st_mode) or (parent / ".git").exists():
                    raise Refused(f"Unsafe host state path {str(root)!r}; preserve it outside repository cleanup. "
                                  f"Inspect path components with ls -ld {shlex.quote(str(root))}; "
                                  "do not replace links, move a checkout or change permissions to force removal.")
        if not root.exists():
            continue
        root_info = root.lstat()
        if root_info.st_uid != os.getuid() or stat.S_IMODE(root_info.st_mode) != 0o700:
            raise Refused(f"Host state {str(root)!r} is not a private owned directory; preserve it.")
        entries = {}
        pending = [root]
        while pending:
            path = pending.pop()
            if path in protected and path not in lab3_paths:
                raise Refused(
                    f"Lab 3 control state {str(path)!r} is preserved; provider-aware Lab 3 removal "
                    "is not implemented. Empty Docker inventory does not prove settlement. "
                    f"Inspect directory metadata with ls -ld {shlex.quote(str(path))}; "
                    "do not delete it or change state roots to bypass this blocker.")
            info = path.lstat()
            if (info.st_uid != os.getuid() or info.st_dev != root_info.st_dev
                    or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))
                    or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1)
                    or stat.S_IMODE(info.st_mode) & 0o022):
                raise Refused(f"Unsafe object under host state {str(root)!r}; preserve the directory.")
            if path.name == ".git" or (path.is_dir() and (path / "lab.sh").exists()):
                raise Refused("Host state contains a source checkout; no source deletion authorized.")
            entries[str(path)] = (info.st_dev, info.st_ino, info.st_mode, info.st_size,
                                  info.st_mtime_ns, info.st_nlink)
            if stat.S_ISDIR(info.st_mode):
                pending.extend(path.iterdir())
        result[str(root)] = entries
    return result


def resource_group(name):
    """Only current, known lifecycle scopes; unknown operations remain global blockers."""
    if name == "secagent-vol" or name in {"secagent-prep-" + part for part in PREPARATION}:
        return "preparation"
    if name in (lab1_setup.CONTAINER, lab1_setup.VOLUME):
        return "lab1"
    match = re.fullmatch(r"secagent-lab2-run([12])-.+", name)
    return "lab2-run" + match[1] if match else None


def validate_image(item, image_id, containers, allowed):
    tags = labels(item, "image")
    if tags.get("org.secagent.owner") != OWNER or tags.get("org.secagent.role") not in IMAGE_ROLES.values():
        raise Refused(f"Image {image_id!r} has unknown workshop ownership/role; preserve it.")
    if identity(item, "image") != image_id:
        raise Refused("Image identity changed; preserve it.")
    family = next(key for key, value in IMAGE_ROLES.items() if value == tags["org.secagent.role"])
    if any(not tag.startswith("secagent-" + family + ":") for tag in (item.get("RepoTags") or [])):
        raise Refused("Workshop image has an unrelated alias; preserve it and inspect its tags.")
    if any(container.get("Image") == image_id and container["Id"] not in allowed
           for container in containers.values()):
        raise Refused("Workshop image is used by an unrelated or preserved container; preserve it.")


def inventory(docker, home, selected_state, *, plan_stops=False, stop_failures=None):
    """Full names/references are observed; private metadata never printed."""
    engine = docker.run(["info", "--format", "{{.ID}}"] ).strip()
    if not engine:
        raise Refused("Selected engine identity is unavailable; no removal.")
    roots = {home / ".local/state/secure-agent-workshop"}
    if selected_state:
        roots.add(Path(selected_state) / "secure-agent-workshop")
    stop_failures = dict(stop_failures or {})
    stops, lab3 = {}, {}
    lab3_resources = {kind: {} for kind in ("container", "network", "volume")}
    for root in roots:
        path = root / "lab3"
        if os.path.lexists(path):
            try:
                planned = lab3_dispose.inventory(docker, path,
                                                 for_stop=plan_stops or "lab3" in stop_failures)
                lab3[str(path)] = planned
            except Exception as error:
                raise Refused("Lab 3 control state is preserved; provider settlement/disposal is unconfirmed. "
                              "Empty Docker inventory does not prove settlement. After the Controller exits, "
                              "use ./lab.sh lab3 stop on its recorded engine. Do not delete control state or "
                              "change roots to bypass this blocker. Inspect directory metadata with ls -ld "
                              + shlex.quote(str(path)) + "; keep private contents out of shared diagnostics.") from error
            for kind, items in lab3[str(path)]["resources"].items():
                if set(items) & lab3_resources[kind].keys():
                    raise Refused("Conflicting Lab 3 selections; preserve both state roots.")
                lab3_resources[kind].update(items)
    if plan_stops and any(
            value["state"]["phase"] not in ("prepared", "stopped", "disposing", "disposed")
            or (value["state"].get("enrollment_attempted") and not value["state"].get("provider_removed"))
            or any(item["State"].get("Running") for item in value["resources"]["container"].values())
            for value in lab3.values()):
        stops["lab3"] = lab3
    selected = {kind: {} for kind in ("container", "network", "volume", "image")}
    containers, groups, blocked_groups = {}, {}, dict(stop_failures)
    preserved = {kind: {} for kind in selected}
    blocked = {}
    unresolved_setup = False

    def hold(kind, name, reason):
        item = selected[kind].pop(name)
        preserved[kind][name] = item
        blocked[kind + " " + name] = reason

    for kind in ("container", "network", "volume"):
        fmt = "{{.Names}}" if kind == "container" else "{{.Name}}"
        args = [kind, "ls", *(["--all"] if kind == "container" else []), "--format", fmt]
        for name in docker.run(args).splitlines():
            if not name:
                continue
            # Container references to selected volumes/images require metadata
            # even when a different project's name is outside our namespace.
            item = inspect(docker, kind, name) if (kind == "container" or name.startswith(
                ("secagent-", "openshell-")) or name in lab3_resources[kind]) else None
            if kind == "container":
                identity(item, kind)  # Incomplete inspection cannot establish safe references.
                containers[item["Id"]] = item
            owned = item is not None and labels(item, kind).get("org.secagent.owner") == OWNER
            native_lab3 = item is not None and str(labels(item, kind).get(
                "openshell.ai/sandbox-namespace", "")).startswith("secagent-lab3-")
            if name.startswith("secagent-") or owned or native_lab3 or name in lab3_resources[kind]:
                group = "lab3" if name in lab3_resources[kind] else resource_group(name)
                groups[kind, name] = group
                identity(item, kind)
                try:
                    validate_resource(item, kind, name, lab3=lab3_resources, for_stop=plan_stops)
                except (Refused, ValueError, lab1_setup.SetupRefused) as error:
                    if group is None:
                        raise Refused("Cannot establish independent cleanup scope. " + str(error)
                                      if isinstance(error, Refused) else
                                      "Unknown resource metadata; preserve all resources and inspect ownership.") from None
                    reason = (str(error) if isinstance(error, Refused) else
                              f"{kind.capitalize()} {name!r} metadata is incompatible; inspect ownership/isolation.")
                    blocked_groups.setdefault(group, reason)
                    part = name.rsplit("-", 1)[-1]
                    known_service = (part in lab2_resources.CONTAINERS
                                     and labels(item, kind).get("org.secagent.role") == "lab2-" + part)
                    if kind == "container" and (group == "preparation" or
                            (group.startswith("lab2-run") and not known_service)):
                        unresolved_setup = True
                selected[kind][name] = item
    generations = {}
    for kind in ("container", "volume", "network"):
        for name, item in selected[kind].items():
            tags = labels(item, kind)
            group = "lab1" if name in (lab1_setup.CONTAINER, lab1_setup.VOLUME) else tags.get("org.secagent.lab2-run")
            if group:
                generation = tags.get("org.secagent.run-id")
                if group in generations and generations[group] != generation:
                    blocked_groups[groups[kind, name]] = "Workshop resource generations conflict; preserve this group."
                generations[group] = generation
    if plan_stops:
        for group in ("lab1", "lab2-run1", "lab2-run2"):
            if group in blocked_groups or not any(
                    groups["container", name] == group and item["State"].get("Running")
                    for name, item in selected["container"].items()):
                continue
            try:
                if group == "lab1":
                    container, volume = lab1_runtime.owned_state(docker)
                    stops[group] = (container, volume)
                else:
                    run = int(group[-1])
                    lab2_state.require_idle(docker, run)
                    stops[group] = lab2_state.existing(docker, run, require_stopped=False, validate_image=False)
                    if stops[group] is None:
                        raise Refused("Selected run disappeared before STOP planning.")
            except (RuntimeError, ValueError, TypeError, LookupError):
                blocked_groups[group] = ("Supported STOP ownership/identity checks failed; preserve this group. "
                                         "Inspect the selected lab's status before another removal plan.")
    if unresolved_setup:
        blocked_groups.setdefault("preparation", "Unresolved setup may still need preparation storage; preserve it.")
    # Fixed lab groups, then actual references. Retaining one group may expose
    # references into another, so repeat until no further group is held.
    while True:
        for kind in ("container", "network", "volume"):
            for name in list(selected[kind]):
                if groups[kind, name] in blocked_groups:
                    hold(kind, name, blocked_groups[groups[kind, name]])
        allowed = {item["Id"] for item in selected["container"].values()}
        previous = set(blocked_groups)
        for item in containers.values():
            if item["Id"] in allowed:
                continue
            references = {"volume": {mount.get("Name") for mount in item.get("Mounts", [])},
                          "network": set((item.get("NetworkSettings") or {}).get("Networks") or {})}
            for kind, names in references.items():
                for name in names & selected[kind].keys():
                    blocked_groups[groups[kind, name]] = (
                        f"Workshop {kind} {name!r} has an unrelated or preserved container reference; preserve its group.")
        for name, item in selected["network"].items():
            if set(item.get("Containers") or {}) - allowed:
                blocked_groups[groups["network", name]] = (
                    f"Workshop network {name!r} has unexpected endpoints; preserve its group.")
        if set(blocked_groups) == previous:
            break
    images = docker.run(["image", "ls", "--all", "--no-trunc", "--format", "{{.ID}} {{.Repository}}:{{.Tag}}"])
    candidates = set()
    for line in images.splitlines():
        image_id, tag = line.split(maxsplit=1)
        if tag.startswith("secagent-"):
            candidates.add(image_id)
    # Include owned dangling images, without assuming every dangling image is ours.
    for image_id in docker.run(["image", "ls", "--all", "--no-trunc", "--quiet",
                                "--filter", "label=org.secagent.owner=" + OWNER]).splitlines():
        candidates.add(image_id)
    for image_id in sorted(candidates):
        item = inspect(docker, "image", image_id)
        identity(item, "image")
        selected["image"][image_id] = item
        try:
            validate_image(item, image_id, containers, allowed)
            if unresolved_setup and labels(item, "image").get("org.secagent.role") in (
                    "preparation-runtime", "preparation-nono", "preparation-openshell", "lab-tools", "lab2-software"):
                raise Refused("Unresolved setup may still need shared software; preserve this image and its aliases.")
        except Refused as error:
            hold("image", image_id, str(error))
    order = {"lab3-site": 0, "lab3-workload": 0, "lab3-gateway": 0, "lab3-ui": 0,
             "lab2-software": 0, "lab-tools": 1, "preparation-openshell": 2,
             "preparation-nono": 3, "preparation-runtime": 4}
    selected["image"] = dict(sorted(selected["image"].items(),
                                   key=lambda pair: order[labels(pair[1], "image")["org.secagent.role"]]))
    host = (host_inventory(home, selected_state, lab3_paths={Path(path) for path in lab3})
            if lab3 else host_inventory(home, selected_state))
    retained_host = host if blocked else {}
    for root in retained_host:
        blocked["host " + root] = "Preserve workshop logs/control evidence while removal is incomplete."
    return {"engine": engine, "resources": selected, "lab3": {} if "lab3" in blocked_groups else lab3,
            "lab3_paths": tuple(sorted(lab3)), "stops": {key: value for key, value in stops.items()
                                                       if key not in blocked_groups},
            "stop_failures": stop_failures, "host": {} if blocked else host, "blocked": blocked,
            "preserved": preserved, "retained_host": retained_host}


def report_reason(message, *, stream=None):
    """Render explicit authored action lines; never infer commands from error prose."""
    stream = sys.stdout if stream is None else stream
    for line in message.splitlines():
        if line.startswith("[NEXT] "):
            next_action(line.removeprefix("[NEXT] "), stream=stream)
        else:
            print(line, file=stream)


def display(snapshot, home, selected_state, *, verbose=False):
    print("Remove workshop data from selected engine:", snapshot["engine"])
    roots = {home / ".local/state/secure-agent-workshop"}
    if selected_state:
        roots.add(Path(selected_state) / "secure-agent-workshop")
    print("Host-state search is limited to these current/default roots (including absent paths):")
    for root in sorted(roots):
        print("  searched scope:", repr(str(root)))
    print("Former custom XDG_STATE_HOME locations are not discovered or deleted. "
          "Inspect any known former workshop state separately; do not delete unrelated paths.")
    if snapshot["stops"]:
        print("STOP after confirmation, before any deletion:")
        for group in snapshot["stops"]:
            print("  supported STOP:", group)
        print("STOP interrupts tasks and may lose unsaved editor work. Save work before confirming.")
        if "lab3" in snapshot["stops"]:
            print("Lab 3 STOP includes local provider cleanup and updates control/evidence in the listed roots. "
                  "Those STOP records are included in the deletion scope; uncertainty preserves the attempt.")
    print("Removable after confirmation and verified STOP (absent resources are skipped):")
    for kind, items in snapshot["resources"].items():
        for name, item in sorted(items.items()):
            detail = f" ({identity(item, kind)})" if verbose and kind != "image" else ""
            print(f"  {kind}: {name!r}" + detail)
            if kind == "image" and item.get("RepoTags"):
                print("    tags: " + ", ".join(repr(tag) for tag in item["RepoTags"]))
    for root, entries in snapshot["host"].items():
        print(f"  host state: {root!r} ({len(entries)} filesystem objects)")
    if snapshot["blocked"]:
        print("Blocked / preserved (NOT authorized for deletion):")
        for resource, reason in sorted(snapshot["blocked"].items()):
            report_reason(f"  {resource!r}: {reason}")
        print("Only the removable subset can be deleted. Cleanup will remain incomplete (nonzero exit).")
    print("Saved credentials, projects, configuration, histories, orders and receipts in the removable subset will be lost.")
    print("Provider keys are NOT revoked. Manually revoke your Ollama/provider credentials "
          "in the provider's account/key settings. Local deletion does not cancel requests already sent.")
    print("Other projects, source checkouts, personal Docker config and unattributed/shared build cache remain.")


def resource_scope(resources):
    """Only the facts that authorize removal; validators check current safety."""
    return {(kind, name): lab_tools.removal_identity(item, kind)
            for kind, items in resources.items() for name, item in items.items()}


def host_scope(snapshot):
    """Pin consented state/control directories, not changing log/file contents."""
    return {name: stamp[:3] for root, entries in (snapshot["host"] or snapshot["retained_host"]).items()
            for name, stamp in entries.items() if name == root or name in snapshot["lab3_paths"]}


def check_plan(before, after, *, remaining=None, attempted=(), failed_stop=False):
    """Revalidated resources must stay inside consent and retain their identities."""
    timing = "during deletion" if remaining is not None else (
        "after STOP began" if attempted else "before any STOP was attempted")
    if before["engine"] != after["engine"]:
        raise Refused("Selected engine identity changed; preserve remaining resources.")
    if before["lab3_paths"] != after["lab3_paths"]:
        raise Refused("Lab 3 control scope changed; preserve remaining resources.")
    if host_scope(before) != host_scope(after) or after["host"].keys() - before["host"].keys():
        raise Refused("Host state directory identity/scope changed; preserve remaining evidence.")
    selected = resource_scope(before["resources"])
    if remaining is not None:
        selected = {key: value for key, value in selected.items() if key[1] in remaining[key[0]]}
    expected = selected | resource_scope(before["preserved"])
    current = resource_scope(after["resources"]) | resource_scope(after["preserved"])
    gone = set()
    if "lab3" in attempted and "lab3" not in after["stop_failures"]:
        # Native supervisor auto-removal is accepted only with verified STOP;
        # Lab 3 inventory independently verifies recorded absence and settlement.
        for planned in before["lab3"].values():
            record = planned["state"]["resources"]
            supervisor = record["containers"].get("supervisor", {})
            if record.get("sandbox_id"):
                gone.update(("container", name) for name, item in planned["resources"]["container"].items()
                            if item["Id"] == supervisor.get("id"))
    gone.difference_update(current)
    changed = (current.keys() - expected.keys()) | (expected.keys() - current.keys() - gone)
    changed.update(key for key in current.keys() & expected.keys() if current[key] != expected[key])
    if changed:
        kind, name = min(changed)
        raise Refused(f"Inventory changed: {kind} {name!r} identity/ownership/dependencies or deletion scope changed "
                      f"{timing}; preserve remaining data.")
    removable = resource_scope(after["resources"]).keys()
    if (removable - selected.keys() or (not failed_stop and removable != selected.keys() - gone)
            or after["stops"].keys() - before["stops"].keys()):
        raise Refused("Removal scope/blockers changed; no expanded deletion or additional STOP is authorized.")


def recheck_removal(docker, home, selected_state, snapshot, remaining_names):
    """Fresh ownership, stopped/settled-state and dependency checks before deletion."""
    current = inventory(docker, home, selected_state, stop_failures=snapshot["stop_failures"])
    check_plan(snapshot, current, remaining=remaining_names)
    return current


def stop_planned(docker, home, selected_state, snapshot, *, verbose=False):
    """Reuse supported STOP, retaining failed groups and all their dependencies."""
    changed, failures = set(), {}
    current = inventory(docker, home, selected_state, plan_stops=True)
    check_plan(snapshot, current)
    for group in ("lab1", "lab2-run1", "lab2-run2", "lab3"):
        if group not in snapshot["stops"]:
            continue
        consented = snapshot["stops"][group]
        changed.add(group)
        progress(f"Attempting consented {group} STOP with recorded identities.", verbose=verbose)
        try:
            if group == "lab1":
                lab1_runtime.stop(docker, consented=consented)
            elif group.startswith("lab2-run"):
                lab2_entry.stop(docker, int(group[-1]), verbose=verbose, consented=consented)
            else:
                for path, planned in sorted(consented.items()):
                    lab3_pipeline.stop(docker, Path(path), consented=planned)
            print("STOP completed:", group, flush=True)
        except Exception:  # noqa: BLE001 - Never expose private subprocess/exception payloads.
            failures[group] = (f"{group} STOP is unconfirmed; preserve this group and its dependencies. "
                               "No forced retry.\n[NEXT] Inspect container status on the selected engine: "
                               f"docker container ls --all --filter name=secagent-{group}\n"
                               "Keep control/evidence; diagnose the STOP outcome before another removal plan.")
            report_reason("[WARN] " + failures[group])
        after = inventory(docker, home, selected_state, plan_stops=True, stop_failures=failures)
        check_plan(current, after, attempted=(group,), failed_stop=group in failures)
        current = after
    settled = inventory(docker, home, selected_state, stop_failures=failures)
    check_plan(current, settled, attempted=changed)
    return settled


def remove(docker, *, home=None, selected_state=None, confirm=None, verbose=False):
    """One in-memory plan, one default-No consent; stop on uncertain effects."""
    home = Path.home() if home is None else Path(home)
    progress("Inventorying selected-engine resources and workshop host-state scope.", verbose=verbose)
    snapshot = inventory(docker, home, selected_state, plan_stops=True)
    display(snapshot, home, selected_state, verbose=verbose)
    if not any(snapshot["resources"].values()) and not snapshot["host"]:
        if snapshot["blocked"]:
            raise Refused("Nothing safely removable; cleanup remains incomplete. Preserved blockers:\n"
                          + "\n".join(snapshot["blocked"].values()))
        return ("No validated workshop resources or host state remain within the displayed scope; "
                "shared cache is not pruned. Manually revoke provider credentials in the provider's key settings.")
    accepted = confirm() if confirm is not None else input("STOP listed labs and delete the listed workshop data? (y/N) ").strip().lower() in ("y", "yes")
    if accepted is not True:
        if snapshot["blocked"]:
            raise Refused("Removal cancelled; nothing deleted. Cleanup remains incomplete; inspect the listed blockers.")
        return "Removal cancelled; nothing deleted."
    progress("Rechecking confirmed scope, identities and blockers before STOP/deletion.", verbose=verbose)
    completed = []
    try:
        snapshot = stop_planned(docker, home, selected_state, snapshot, verbose=verbose)
        if snapshot["lab3"]:
            for path, planned in snapshot["lab3"].items():
                progress("Revalidating settled Lab 3 disposal.", verbose=verbose)
                lab3_dispose.dispose(docker, Path(path), planned)
                completed.append("Lab 3 resources " + path)
            remaining_names = {kind: set(items) for kind, items in snapshot["resources"].items()}
            for planned in snapshot["lab3"].values():
                for kind, items in planned["resources"].items():
                    remaining_names[kind].difference_update(items)
            snapshot = recheck_removal(docker, home, selected_state, snapshot, remaining_names)
        remaining_names = {kind: set(items) for kind, items in snapshot["resources"].items()}
        for kind in ("container", "network", "volume", "image"):
            for name, before in snapshot["resources"][kind].items():
                progress(f"Rechecking {kind} {name!r} before removal.", verbose=verbose)
                recheck_removal(docker, home, selected_state, snapshot, remaining_names)
                if docker.run(["info", "--format", "{{.ID}}"] ).strip() != snapshot["engine"]:
                    raise Refused("Selected engine identity changed.")
                current = inspect(docker, kind, name)
                if (identity(current, kind) != identity(before, kind)
                        or labels(current, kind) != labels(before, kind)):
                    raise Refused(f"{kind.capitalize()} {name!r} identity or labels changed after confirmation; preserve it.")
                if kind != "image":
                    validate_resource(current, kind, name)
                if kind in ("volume", "network"):
                    refs = docker.run(["container", "ls", "--all", "--quiet", "--filter", kind + "=" + name])
                    if refs.strip() or (kind == "network" and current.get("Containers")):
                        raise Refused(f"{kind.capitalize()} {name!r} still has container references; preserve it.")
                if kind == "image":
                    if sorted(current.get("RepoTags") or []) != sorted(before.get("RepoTags") or []):
                        raise Refused(f"Image {name!r} aliases changed after confirmation; inspect its tags and preserve it.")
                    # Remove aliases explicitly, never force image deletion or prune parents.
                    pending_tags = list(current.get("RepoTags") or [])
                    for target in current.get("RepoTags") or [name]:
                        recheck_removal(docker, home, selected_state, snapshot, remaining_names)
                        fresh = inspect(docker, "image", name)
                        if sorted(fresh.get("RepoTags") or []) != sorted(pending_tags):
                            raise Refused("Image aliases changed during removal; preserve remaining aliases.")
                        if identity(inspect(docker, "image", target), "image") != name:
                            raise Refused(f"Image tag {target!r} binding changed before removal; preserve the current image.")
                        for reference in docker.run(["container", "ls", "--all", "--no-trunc", "--quiet"]).splitlines():
                            if inspect(docker, "container", reference).get("Image") == name:
                                raise Refused(f"Image {name!r} gained a container reference; inspect its containers and preserve it.")
                        docker.run(["image", "rm", "--no-prune", target], timeout=None)
                        if target in pending_tags:
                            pending_tags.remove(target)
                        snapshot["resources"]["image"][name]["RepoTags"] = list(pending_tags)
                else:
                    target = name if kind == "volume" else current["Id"]
                    docker.run([kind, "rm", target], timeout=None)
                remaining_names[kind].remove(name)
                completed.append(f"{kind} {name}")
                print("Removed:", completed[-1], flush=True)
        recheck_removal(docker, home, selected_state, snapshot, remaining_names)
        host_now = (host_inventory(home, selected_state, lab3_paths={Path(path) for path in snapshot["lab3_paths"]})
                    if snapshot["lab3_paths"] else host_inventory(home, selected_state))
        if host_scope(snapshot) != host_scope(snapshot | {"host": host_now, "retained_host": {}}):
            raise Refused("Host state directory identity changed; preserve remaining files.")
        # Consent covers these owned directories. Re-scan after Docker cleanup;
        # retain all host evidence whenever a resource group is still blocked.
        for root, entries in ({} if snapshot["blocked"] else host_now).items():
            progress(f"Rechecking host-state identities under {root!r}.", verbose=verbose)
            for name in sorted(entries, key=lambda value: len(Path(value).parts), reverse=True):
                path = Path(name)
                # Recheck ancestors immediately before unlink/rmdir; never follow links.
                if any(not stat.S_ISDIR(parent.lstat().st_mode) for parent in path.parents):
                    raise Refused(f"Host state ancestor of {str(path)!r} changed; inspect path safety, remaining data preserved.")
                info = path.lstat()
                before = entries[name]
                if (info.st_dev, info.st_ino, info.st_mode) != before[:3]:
                    raise Refused(f"Host state identity at {str(path)!r} changed; inspect the path, remaining data preserved.")
                if stat.S_ISDIR(info.st_mode):
                    path.rmdir()
                else:
                    if (info.st_size, info.st_mtime_ns, info.st_nlink) != before[3:]:
                        raise Refused(f"Host state file {str(path)!r} changed; inspect the path, remaining data preserved.")
                    path.unlink()
            completed.append("host state " + root)
            print("Removed:", completed[-1], flush=True)
        progress("Verifying final removal and preserved-resource inventory.", verbose=verbose)
        remaining = inventory(docker, home, selected_state, stop_failures=snapshot["stop_failures"])
        if any(remaining["resources"].values()) or remaining["host"]:
            raise Refused("Workshop resources remain; removal is incomplete.")
        if resource_scope(remaining["preserved"]) != resource_scope(snapshot["preserved"]):
            raise Refused("Preserved resource identities/dependencies changed; removal is incomplete.")
    except (Exception, KeyboardInterrupt) as error:
        print(f"Removal incomplete or uncertain after {len(completed)} completed resource groups. "
              "Keep remaining resources; do not force deletion or repeat an uncertain operation. "
              "Review the printed progress and inspect remaining selected-engine identities.", file=sys.stderr)
        if isinstance(error, (Refused, lab2_state.Refused, KeyboardInterrupt)):
            raise
        raise Refused("No successful workshop removal is claimed; private error details excluded.") from None
    if snapshot["blocked"]:
        print("Still preserved:", flush=True)
        for resource, reason in sorted(snapshot["blocked"].items()):
            report_reason(f"  {resource!r}: {reason}")
        raise Refused("Partial removal: confirmed removable resources deleted; blocked resources and evidence remain. "
                      "Cleanup is incomplete. Inspect the listed blockers; no automatic reservation recovery or retry.")
    return ("Validated workshop resources and host state removed within the displayed scope. "
            "Shared/unattributed cache was not pruned. Manually revoke provider credentials "
            "in the provider's key settings.")


def release_reservations(docker):
    """Explicit operator-confirmed release only; never infer operation settlement."""
    engine = docker.run(["info", "--format", "{{.ID}}" ]).strip()
    if not engine:
        raise Refused("Reservation release needs a confirmed engine; inspect Docker status.")
    planned = []
    for run in (1, 2):
        name = f"secagent-lab2-run{run}-setup-reservation"
        if not docker.inventory("container", name):
            continue
        item = inspect(docker, "container", name)
        tags = labels(item, "container")
        if (tags.get("org.secagent.owner") != OWNER
                or tags.get("org.secagent.role") != "lab2-setup-reservation"
                or tags.get("org.secagent.lab2-run") != str(run)
                or not re.fullmatch(r"[a-f0-9]{32}", tags.get("org.secagent.reservation", ""))):
            raise Refused(f"Reservation {name!r} ownership is unconfirmed; preserve it and inspect its labels.")
        identity(item, "container")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", item.get("Image", "")):
            raise Refused(f"Reservation {name!r} image identity is unconfirmed; preserve it and inspect its metadata.")
        planned.append((run, name, item))

    def recheck():
        if docker.run(["info", "--format", "{{.ID}}" ]).strip() != engine:
            raise Refused("Reservation engine changed; preserve markers and inspect the selected endpoint.")
        for run, name, item in planned:
            lab2_state.require_idle(docker, run, allow_reservation=True)
            try:
                lab2_setup.reservation_metadata(docker, name, item["Id"], item["Image"], labels(item, "container"))
            except lab2_setup.Uncertain as error:
                raise Refused(str(error)) from None

    recheck()
    if not planned:
        print("No Lab 2 reservation markers found; continuing normal removal.")
        return True
    print("Release Lab 2 reservation markers on engine:", engine)
    for _, name, item in planned:
        print(f"  {name}: {item['Id']}")
    print("Confirm the previous setup/reset has settled and no Docker operation is outstanding. "
          "Stopped/Created status or missing workers does NOT prove settlement. If unsure, decline.")
    print("Only these markers will be deleted, not lab data/images. Normal uninstall asks separately. "
          "Declining uninstall later does not restore released markers.")
    if input("Confirm settlement and release these markers? (y/N) ").strip().lower() not in ("y", "yes"):
        print("Reservation release cancelled; no uninstall attempted.")
        return False
    try:
        while planned:
            recheck()  # Validate all remaining markers before each exact-ID deletion.
            _, name, item = planned[0]
            docker.run(["container", "rm", item["Id"]])
            if (docker.run(["info", "--format", "{{.ID}}" ]).strip() != engine
                    or docker.inventory("container", name)):
                raise Refused("Reservation deletion was not confirmed.")
            planned.pop(0)
            print("Released reservation:", name, flush=True)
    except (Exception, KeyboardInterrupt):  # noqa: BLE001 - Keep private Docker diagnostics out of partial-release errors.
        raise Refused("Reservation release incomplete or uncertain; no uninstall attempted. "
                      "Earlier markers may already be removed. Keep remaining resources; inspect selected-engine "
                      "container status before another operation. No forced retry; private details excluded.") from None
    return True


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--release-reservations", action="store_true")
    options = parser.parse_args(args)
    if not all(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr)):
        parser.error("Removal requires an interactive terminal; nothing removed")
    try:
        docker = lab_tools.Docker(options.endpoint)
        if options.release_reservations and not release_reservations(docker):
            return 0
        print(remove(docker, selected_state=os.environ.get("XDG_STATE_HOME"),
                     verbose=options.verbose))
        return 0
    except (EOFError, KeyboardInterrupt):
        print("Removal cancelled or interrupted; retain remaining resources and review printed progress.", file=sys.stderr)
        return 130
    except (Refused, lab2_state.Refused) as error:
        report_reason(str(error), stream=sys.stderr)
    except Exception:  # noqa: BLE001 - Docker/filesystem failures may contain private metadata.
        print("Workshop removal refused or incomplete. Preserve resources and inspect selected-engine "
              "ownership/status and workshop host-state path safety; private details excluded.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
