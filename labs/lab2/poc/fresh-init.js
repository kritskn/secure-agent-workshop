// Seeded once in a fresh Lab 2 HOME; later user layouts are preserved.
// Plain folder sessions only: no terminals, agents, worktrees or model calls.
const protectedRun = {{PROTECTED_RUN}};
const project = "/home/lab-user/workshop/lab2";
const sandbox = "/home/lab-user/policy";
const marker = "lab2_workspace_initialized";
let pending = false;
let originalWindow;
let dock;

editor.on("ready", () => {
  if (pending || editor.getCwd() !== project || editor.getGlobalState(marker)) return;
  const windows = editor.listWindows();
  if (windows.length !== 1 || windows[0].root !== project) {
    editor.setStatus("Lab 2: existing workspace layout preserved.");
    return;
  }
  dock = editor.getPluginApi("orchestrator");
  if (!dock) {
    editor.setStatus("Lab 2: workspace dock unavailable; no changes.");
    return;
  }
  originalWindow = editor.activeWindow();
  if (!protectedRun) {
    dock.renameWorkspace(originalWindow, "Lab 2");
    editor.setGlobalState(marker, true);
    return;
  }
  pending = true;
  if (!editor.createWindow(sandbox, "Sandbox")) {
    pending = false;
    editor.setStatus("Lab 2: workspace creation was not queued.");
  }
});

editor.on("window_created", async (window) => {
  if (!pending || window.root !== sandbox) return;
  pending = false;
  dock.renameWorkspace(originalWindow, "Lab 2");
  editor.setActiveWindow(window.id);
  await editor.flush();
  editor.executeAction("focus_file_explorer");
  editor.openFileInBackground(sandbox + "/nono.json");
  editor.openFile(sandbox + "/README.md");
  await editor.flush();
  editor.setActiveWindow(originalWindow);
  await editor.flush();
  editor.setGlobalState(marker, true);
});
