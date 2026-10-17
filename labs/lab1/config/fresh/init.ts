// Deployed by setup; existing layout markers and user layouts are preserved.
// Plain folder sessions only: no terminals, agents, worktrees or model calls.
const project = "/home/lab-user/workshop/lab1";
const skills = "/home/lab-user/.agents/skills";
const marker = "lab1_workspace_initialized";
let pending = false;
let originalWindow;
let dock;

editor.on("ready", () => {
  if (pending || editor.getCwd() !== project || editor.getGlobalState(marker)) return;
  const windows = editor.listWindows();
  if (windows.length !== 1 || windows[0].root !== project) {
    editor.setStatus("Lab 1: existing workspace layout preserved.");
    return;
  }
  dock = editor.getPluginApi("orchestrator");
  if (!dock) {
    editor.setStatus("Lab 1: workspace dock unavailable; no changes.");
    return;
  }
  originalWindow = editor.activeWindow();
  pending = true;
  if (!editor.createWindow(skills, "Skills")) {
    pending = false;
    editor.setStatus("Lab 1: workspace creation was not queued.");
  }
});

editor.on("window_created", async (window) => {
  if (!pending || window.root !== skills) return;
  pending = false;
  dock.renameWorkspace(originalWindow, "Lab 1");
  editor.setActiveWindow(window.id);
  await editor.flush();
  editor.executeAction("focus_file_explorer");
  await editor.flush();
  editor.setActiveWindow(originalWindow);
  await editor.flush();
  editor.openFile(project + "/README.md");
  editor.setGlobalState(marker, true);
});
