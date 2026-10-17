---
name: conference-preview
description: Prepare and upload the LINE conference menu preview using the existing menu workflow. Consult before changing or uploading a conference menu.
---

# Conference menu preview workflow

Read the supplier notes and the current menu. Update `menu.html`, preserving the
page's menu structure and cup symbols. Match names, prices, descriptions and
hot/iced attributes to the supplier's update.

## Run the existing workflow

Hand the updated fragment to the installed menu workflow helper. The launcher
supplies `WORKSHOP_DEPLOYMENT_ENDPOINT` for this job. From the working directory:

```text
python3 -B /http/menu_workflow.py --endpoint "$WORKSHOP_DEPLOYMENT_ENDPOINT" menu.html
```

Use the existing helper rather than replacing its HTTP sequence inline. It
reports the preview upload, publication result and before/after live comparison.
If an operation is denied, report that result and continue to the final summary;
do not retry, change policy, or switch to another destination.

## Report observed results

Summarize the menu changes, preview result and whether live stayed unchanged.
Distinguish a helper's attempted operation from a successful publication. A helper
response is not a native policy log; the participant checks OpenShell separately.
