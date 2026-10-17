// Seed once in a fresh operator HOME; preserve restored buffers/layout thereafter.
// Public walkthrough files only: no private gateway HOME, terminals or agent calls.
const project = "/home/lab-user/workshop/lab3";
const marker = "lab3_walkthrough_initialized";

editor.on("ready", () => {
  if (editor.getCwd() !== project || editor.getGlobalState(marker)) return;
  const windows = editor.listWindows();
  if (windows.length !== 1 || windows[0].root !== project) {
    editor.setStatus("Lab 3: existing workspace layout preserved.");
    return;
  }
  editor.openFileInBackground(project + "/openshell/policy.yaml");
  editor.openFileInBackground(project + "/openshell/provider.json");
  editor.openFile(project + "/README.md");
  editor.setGlobalState(marker, true);
});
