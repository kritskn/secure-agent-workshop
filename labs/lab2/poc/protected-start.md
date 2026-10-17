**Run 2 only — Protected access.** Do not start protected Pi inside Run 1.
Complete step 5's file-grant reduction, network/ENV edits and
read-only credential walkthrough. Remove `/home/lab-user/` from the grants
before any profiled launch. Save with **Ctrl+S**, then reproduce the bug.
Do not start a second protected Pi if one is already running.

In Agent, launch with your saved policy:

```bash
{{LAUNCH}}
```

Do not replace it with plain `pi`. Entry validated guest/provider/private-file
state without starting Pi; it does **not** verify completion of the policy
exercise. The Agent shell provides the synthetic inherited flag.
If provider/auth/key state changes after entry, stop and request revalidation;
this raw command does not repeat the entry checks.
