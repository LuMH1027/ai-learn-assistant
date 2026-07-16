let courses = [];
let activeCourse = null;
let activeFile = null;
let pendingChatFiles = [];
let requestBusy = false;
let previewRequestVersion = 0;

const $ = (id) => document.getElementById(id);
const LAYOUT_STORAGE_KEY = "local-course-agent-layout-v1";
const CONTENT_SHARE = 98.8;
const DEFAULT_LAYOUT = { sidebar: 22, preview: 31, previewOpen: true };
const hasStoredLayout = localStorage.getItem(LAYOUT_STORAGE_KEY) !== null;
const layoutState = readLayoutState();

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "请求失败");
  return data;
}

async function loadConfig() {
  const config = await api("/api/config");
  $("rootFolder").value = config.root_folder || "";
  $("aiStatus").textContent = `AI：${config.ai_configured ? "已配置" : "轻量回答"}`;
  $("mineruStatus").textContent = `MinerU：${config.mineru_configured ? "已配置" : config.mineru_auto ? "自动" : "关闭"}`;
}

async function loadCourses() {
  const data = await api("/api/courses");
  courses = data.courses;
  if (activeCourse) {
    activeCourse = courses.find((course) => course.id === activeCourse.id) || null;
  }
  renderCourses();
  renderActiveFileTree();
}

function renderCourses() {
  const host = $("courseList");
  if (!courses.length) {
    host.className = "course-list empty";
    host.textContent = "未发现课程，请检查资料根目录。";
    return;
  }
  host.className = "course-list";
  host.replaceChildren();
  for (const course of courses) {
    const wrapper = document.createElement("div");
    wrapper.className = "course";
    const header = document.createElement("div");
    header.className = "course-header" + (activeCourse?.id === course.id ? " active" : "");
    header.tabIndex = 0;
    header.role = "button";
    header.setAttribute("aria-pressed", activeCourse?.id === course.id ? "true" : "false");
    header.title = course.name;
    header.innerHTML = `<span class="course-main"><span class="course-icon" aria-hidden="true">▤</span><span class="course-label">${escapeHtml(course.name)}</span></span><span class="course-count">${course.file_count} 个</span>`;
    header.onclick = () => selectCourse(course);
    header.onkeydown = (event) => activateOnKeyboard(event, () => selectCourse(course));
    wrapper.appendChild(header);
    host.appendChild(wrapper);
  }
  renderLayout();
}

function renderActiveFileTree() {
  const host = $("activeFileTree");
  if (!activeCourse) {
    host.className = "file-tree empty";
    host.textContent = "选择课程后显示文件";
    return;
  }
  host.className = "file-tree";
  host.replaceChildren(renderNodes(activeCourse.children || []));
  if (!activeCourse.children?.length) {
    host.className = "file-tree empty";
    host.textContent = "当前课程还没有资料";
  }
  renderLayout();
}

function renderNodes(nodes) {
  const fragment = document.createDocumentFragment();
  for (const node of nodes) {
    if (node.type === "folder") {
      const group = document.createElement("details");
      group.className = "tree-group";
      group.open = true;
      const summary = document.createElement("summary");
      summary.className = "tree-node folder";
      summary.innerHTML = `<span class="file-icon" aria-hidden="true">▸</span><span class="file-label">${escapeHtml(node.name)}</span>`;
      group.append(summary, renderNodes(node.children || []));
      fragment.appendChild(group);
      continue;
    }
    const item = document.createElement("div");
    item.className = `tree-node file${activeFile?.id === node.id ? " active" : ""}`;
    item.tabIndex = 0;
    item.role = "button";
    item.title = node.name;
    item.setAttribute("aria-label", `预览文件 ${node.name}`);
    item.innerHTML = `<span class="file-icon" aria-hidden="true">${fileGlyph(node.extension)}</span><span class="file-label">${escapeHtml(node.name)}</span>`;
    item.onclick = () => previewFile(node);
    item.onkeydown = (event) => activateOnKeyboard(event, () => previewFile(node));
    fragment.appendChild(item);
  }
  return fragment;
}

function fileGlyph(extension = "") {
  if (extension === ".pdf") return "PDF";
  if ([".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"].includes(extension)) return "IMG";
  return "TXT";
}

function activateOnKeyboard(event, callback) {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    callback();
  }
}

async function selectCourse(course) {
  activeCourse = course;
  resetCourseContext();
  $("agentTitle").textContent = course.name;
  $("courseMeta").textContent = `${course.file_count} 个文件 · 独立会话与记忆`;
  for (const id of ["indexCourse", "sendQuestion", "saveNote", "notesToggle", "generateSummary", "generateQuiz"]) {
    $(id).disabled = false;
  }
  setBusy(requestBusy);
  $("courseDropZone").classList.add("ready");
  $("courseDropZone").textContent = `拖入文件，加入「${course.name}」`;
  renderCourses();
  renderActiveFileTree();
  closeMobileSidebar();
  await Promise.all([loadMessages(course.id), loadNotes(course.id)]);
}

function resetCourseContext() {
  previewRequestVersion += 1;
  activeFile = null;
  pendingChatFiles = [];
  hideChatDropState();
  $("previewTitle").textContent = "资料预览";
  $("previewHint").textContent = "选择文件后在此阅读";
  $("preview").className = "preview-content preview-empty";
  $("preview").textContent = "选择左侧资料，或点击回答中的引用。";
  $("previewSources").textContent = "回答中的引用会显示在这里。";
  $("previewInfo").textContent = "选择文件后显示文件信息。";
  $("messages").innerHTML = '<div class="message-empty">正在加载课程会话…</div>';
  $("notesList").textContent = "正在加载课程笔记…";
  setPreviewTab("file");
}

async function previewFile(file, options = {}) {
  const requestVersion = ++previewRequestVersion;
  const courseId = activeCourse?.id;
  const fileId = file.id;
  activeFile = file;
  closeMobileSidebar();
  setPreviewOpen(true);
  setPreviewTab("file");
  $("previewTitle").textContent = file.name;
  $("previewHint").textContent = file.extension?.slice(1).toUpperCase() || "课程资料";
  renderActiveFileTree();
  renderPreviewInfo(file);
  const url = `/api/files/preview?id=${encodeURIComponent(file.id)}`;
  const page = options.page ? `#page=${encodeURIComponent(options.page)}` : "";
  if (file.extension === ".pdf") {
    $("preview").className = "preview-content";
    $("preview").innerHTML = `<div class="pdf-preview"><iframe src="${url}${page}" title="${escapeHtml(file.name)}"></iframe><a class="pdf-fallback" href="${url}${page}" target="_blank" rel="noopener">在新窗口打开 PDF</a></div>`;
    return true;
  }
  if ([".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"].includes(file.extension)) {
    $("preview").className = "preview-content";
    $("preview").innerHTML = `<div class="image-preview-wrap"><img class="image-preview" src="${url}" alt="${escapeHtml(file.name)}" /></div>`;
    return true;
  }
  const text = await fetch(url).then((response) => response.text());
  if (
    requestVersion !== previewRequestVersion ||
    activeCourse?.id !== courseId ||
    activeFile?.id !== fileId
  ) return false;
  $("preview").className = "preview-content";
  $("preview").innerHTML = `<pre class="text-preview">${escapeHtml(text)}</pre>`;
  return true;
}

function renderPreviewInfo(file) {
  $("previewInfo").innerHTML = `<dl class="file-info"><dt>文件名</dt><dd>${escapeHtml(file.name)}</dd><dt>类型</dt><dd>${escapeHtml(file.extension || "未知")}</dd></dl>`;
}

function setPreviewTab(name) {
  const tabs = { file: "preview", sources: "previewSources", info: "previewInfo" };
  for (const [key, panelId] of Object.entries(tabs)) {
    const tab = $(`previewTab${key[0].toUpperCase()}${key.slice(1)}`);
    const selected = key === name;
    tab.classList.toggle("active", selected);
    tab.setAttribute("aria-selected", selected ? "true" : "false");
    $(panelId).hidden = !selected;
  }
}

function setupPreviewTabs() {
  $("previewTabFile").onclick = () => setPreviewTab("file");
  $("previewTabSources").onclick = () => setPreviewTab("sources");
  $("previewTabInfo").onclick = () => setPreviewTab("info");
}

async function loadMessages(courseId = activeCourse?.id) {
  if (!courseId) return;
  const data = await api(`/api/courses/${courseId}/messages`);
  if (activeCourse?.id !== courseId) return;
  renderMessages(data.messages);
}

async function loadNotes(courseId = activeCourse?.id) {
  if (!courseId) return;
  const data = await api(`/api/courses/${courseId}/notes`);
  if (activeCourse?.id !== courseId) return;
  const host = $("notesList");
  host.replaceChildren();
  if (!data.notes.length) {
    host.textContent = "暂无笔记。";
    return;
  }
  for (const note of data.notes) {
    const item = document.createElement("div");
    item.className = "note-item";
    item.textContent = `${note.title}：${note.content.slice(0, 80)}`;
    host.appendChild(item);
  }
}

function renderMessages(messages) {
  const host = $("messages");
  host.replaceChildren();
  if (!messages.length) {
    host.innerHTML = `<div class="message-empty">在「${escapeHtml(activeCourse?.name || "当前课程")}」中提问。回答会优先引用课程资料，并保存在本地。</div>`;
    return;
  }
  for (const message of messages) appendMessage(message.role, message.content, message.citations || [], message.trace || []);
  host.scrollTop = host.scrollHeight;
}

function appendMessage(role, content, citations = [], trace = []) {
  const node = document.createElement("div");
  node.className = `message ${role}`;
  node.textContent = content;
  if (trace.length) node.appendChild(renderTrace(trace));
  for (const citation of citations) {
    const link = document.createElement("button");
    link.type = "button";
    link.className = "citation";
    link.textContent = `来源：${citation.file_name}${citation.page ? ` · 第 ${citation.page} 页` : ""} · 片段 ${citation.chunk_index}`;
    link.onclick = () => previewByCitation(citation);
    node.appendChild(link);
  }
  $("messages").appendChild(node);
}

function renderTrace(trace) {
  const rail = document.createElement("div");
  rail.className = "trace-rail";
  for (const step of trace) {
    const item = document.createElement("div");
    item.className = `trace-step ${step.status}`;
    item.innerHTML = `<span>${escapeHtml(step.label)}</span><small>${escapeHtml(step.detail)}</small>`;
    rail.appendChild(item);
  }
  return rail;
}

function previewByCitation(citation) {
  const courseId = activeCourse?.id;
  const fileId = citation.file_id;
  const file = findFile(courses, citation.file_id);
  if (file) {
    previewFile(file, { page: citation.page })
      .then((rendered) => {
        if (!rendered || activeCourse?.id !== courseId || activeFile?.id !== fileId) return;
        setPreviewSources(citation);
        setPreviewTab("sources");
      })
      .catch((error) => showToast(error.message));
  }
}

function setPreviewSources(citation) {
  const file = findFile(courses, citation.file_id);
  const host = $("previewSources");
  host.innerHTML = file
    ? `<blockquote class="source-quote">${escapeHtml(citation.quote || "该引用未提供原文片段。")}</blockquote><button class="source-item" type="button">${escapeHtml(file.name)}${citation.page ? ` · 第 ${citation.page} 页` : ""}</button>`
    : "没有可显示的引用。";
  const button = host.querySelector(".source-item");
  if (button && file) button.onclick = () => previewFile(file, { page: citation.page });
}

function findFile(courseList, fileId) {
  for (const course of courseList) {
    const found = findFileInNodes(course.children, fileId);
    if (found) return found;
  }
  return null;
}

function findFileInNodes(nodes, fileId) {
  for (const node of nodes || []) {
    if (node.type === "file" && node.id === fileId) return node;
    if (node.type === "folder") {
      const found = findFileInNodes(node.children, fileId);
      if (found) return found;
    }
  }
  return null;
}

async function saveRoot() {
  await api("/api/config", { method: "POST", body: JSON.stringify({ root_folder: $("rootFolder").value }) });
  activeCourse = null;
  resetCourseContext();
  $("agentTitle").textContent = "课程 Agent";
  $("courseMeta").textContent = "选择一门课程开始学习";
  $("courseDropZone").classList.remove("ready");
  $("courseDropZone").textContent = "拖入文件，加入当前课程";
  for (const id of ["indexCourse", "sendQuestion", "saveNote", "notesToggle", "generateSummary", "generateQuiz"]) {
    $(id).disabled = true;
  }
  await loadCourses();
}

async function indexActiveCourse() {
  if (!activeCourse || requestBusy) return;
  setBusy(true);
  $("indexCourse").textContent = "入库中…";
  try {
    const data = await api(`/api/courses/${activeCourse.id}/index`, { method: "POST" });
    showToast(`知识库完成：${data.indexed_files} 个文件，${data.total_chunks} 个片段`);
  } finally {
    $("indexCourse").textContent = "构建知识库";
    setBusy(false);
  }
}

async function sendQuestion() {
  if (!activeCourse || requestBusy) return;
  const question = $("question").value.trim();
  if (!question && !pendingChatFiles.length) return;
  $("question").value = "";
  setBusy(true);
  try {
    if (pendingChatFiles.length) {
      const form = new FormData();
      form.append("question", question);
      form.append("mode", $("chatMode").value);
      for (const file of pendingChatFiles) form.append("files", file, file.name);
      pendingChatFiles = [];
      hideChatDropState();
      await postForm(`/api/courses/${activeCourse.id}/chat`, form);
    } else {
      await api(`/api/courses/${activeCourse.id}/chat`, {
        method: "POST",
        body: JSON.stringify({ question, mode: $("chatMode").value }),
      });
    }
    await loadMessages();
  } finally {
    setBusy(false);
  }
}

async function generateStudyArtifact(type) {
  if (!activeCourse || requestBusy) return;
  const path = type === "summary" ? "summary" : "quiz";
  setBusy(true);
  try {
    const data = await api(`/api/courses/${activeCourse.id}/${path}`, { method: "POST" });
    if (data.courses) courses = data.courses;
    activeCourse = courses.find((course) => course.id === activeCourse.id) || activeCourse;
    renderCourses();
    renderActiveFileTree();
    await loadMessages();
    showToast(`${type === "summary" ? "课程摘要" : "练习题"}已保存：${data.artifact?.name || "AI生成"}`);
  } finally {
    setBusy(false);
  }
}

async function saveNote() {
  if (!activeCourse) return;
  const title = $("noteTitle").value.trim() || "学习笔记";
  const content = $("noteContent").value.trim();
  if (!content) return;
  await api(`/api/courses/${activeCourse.id}/notes`, { method: "POST", body: JSON.stringify({ title, content }) });
  $("noteTitle").value = "";
  $("noteContent").value = "";
  await loadNotes();
  showToast("笔记已保存到当前课程。 ");
}

async function postForm(path, form) {
  const response = await fetch(path, { method: "POST", body: form });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "请求失败");
  return data;
}

async function uploadCourseFiles(files) {
  if (!activeCourse || !files.length) return;
  const form = new FormData();
  for (const file of files) form.append("files", file, file.name);
  const data = await postForm(`/api/courses/${activeCourse.id}/files`, form);
  showToast(`已加入：${data.saved.map((item) => item.name).join("、")}`);
  courses = data.courses || courses;
  activeCourse = courses.find((course) => course.id === activeCourse.id) || activeCourse;
  renderCourses();
  renderActiveFileTree();
}

function setupFilePickers() {
  $("courseFilePickerButton").onclick = () => $("courseFilePicker").click();
  $("courseFilePicker").onchange = (event) => {
    uploadCourseFiles([...event.target.files]).catch((error) => showToast(error.message));
    event.target.value = "";
  };
  $("chatFilePickerButton").onclick = () => $("chatFilePicker").click();
  $("chatFilePicker").onchange = (event) => {
    pendingChatFiles = [...event.target.files];
    showPendingChatFiles();
    event.target.value = "";
  };
}

function setupDragAndDrop() {
  const courseDrop = $("courseDropZone");
  courseDrop.addEventListener("dragover", (event) => {
    event.preventDefault();
    courseDrop.classList.add("dragging");
  });
  courseDrop.addEventListener("dragleave", () => courseDrop.classList.remove("dragging"));
  courseDrop.addEventListener("drop", (event) => {
    event.preventDefault();
    courseDrop.classList.remove("dragging");
    uploadCourseFiles([...event.dataTransfer.files]).catch((error) => showToast(error.message));
  });
  const composer = document.querySelector(".composer");
  composer.addEventListener("dragover", (event) => {
    event.preventDefault();
    composer.classList.add("dragging");
    $("chatDropHint").classList.add("show");
  });
  composer.addEventListener("dragleave", hideChatDropState);
  composer.addEventListener("drop", (event) => {
    event.preventDefault();
    pendingChatFiles = [...event.dataTransfer.files];
    composer.classList.remove("dragging");
    showPendingChatFiles();
  });
}

function showPendingChatFiles() {
  $("chatDropHint").classList.add("show");
  $("chatDropHint").textContent = `已附加 ${pendingChatFiles.length} 个文件，发送后临时读取。`;
}

function hideChatDropState() {
  document.querySelector(".composer").classList.remove("dragging");
  $("chatDropHint").classList.remove("show");
  $("chatDropHint").textContent = "松开后临时读取附件，不写入课程目录";
}

function readLayoutState() {
  try {
    return { ...DEFAULT_LAYOUT, ...JSON.parse(localStorage.getItem(LAYOUT_STORAGE_KEY) || "{}") };
  } catch {
    return { ...DEFAULT_LAYOUT };
  }
}

function saveLayoutState() {
  localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(layoutState));
}

function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}

function measureCompactSidebarShare() {
  const candidates = [...document.querySelectorAll(".brand-mark, .icon-button, .course-icon, .file-icon, .picker-icon")];
  const widest = candidates.reduce((width, element) => Math.max(width, element.getBoundingClientRect().width), 34);
  return clamp(((widest + 18) / Math.max(window.innerWidth, 1)) * 100, 5.5, 11.5);
}

function centerShare() {
  return CONTENT_SHARE - layoutState.sidebar - (layoutState.previewOpen ? layoutState.preview : 0);
}

function renderLayout() {
  const workspace = $("appWorkspace");
  const mobile = window.matchMedia("(max-width: 60rem)").matches;
  const minimumSidebar = measureCompactSidebarShare();
  layoutState.sidebar = clamp(Number(layoutState.sidebar) || DEFAULT_LAYOUT.sidebar, minimumSidebar, 30);
  layoutState.preview = clamp(Number(layoutState.preview) || DEFAULT_LAYOUT.preview, 20, 44);
  if (layoutState.previewOpen) {
    layoutState.sidebar = Math.min(layoutState.sidebar, CONTENT_SHARE - layoutState.preview - 34);
  }
  workspace.style.setProperty("--sidebar-share", `${layoutState.sidebar}%`);
  workspace.style.setProperty("--preview-share", `${layoutState.preview}%`);
  workspace.classList.toggle("sidebar-compact", !mobile && layoutState.sidebar < 14);
  workspace.classList.toggle("preview-closed", !layoutState.previewOpen);
  $("previewToggle").setAttribute("aria-pressed", layoutState.previewOpen ? "true" : "false");
  $("previewToggle").setAttribute("aria-label", layoutState.previewOpen ? "关闭资料预览" : "打开资料预览");
  $("rightResizer").setAttribute("aria-valuenow", String(Math.round(layoutState.preview)));
  $("leftResizer").setAttribute("aria-valuenow", String(Math.round(layoutState.sidebar)));
  $("leftResizer").setAttribute("aria-valuemin", String(Math.round(minimumSidebar)));
  $("leftResizer").setAttribute("aria-valuemax", "30");
  $("rightResizer").setAttribute("aria-valuemin", "20");
  $("rightResizer").setAttribute("aria-valuemax", "44");
  $("courseSidebar").toggleAttribute("inert", mobile && !workspace.classList.contains("sidebar-open"));
  $("agentPanel").toggleAttribute("inert", mobile && layoutState.previewOpen);
  $("previewPanel").toggleAttribute("inert", !layoutState.previewOpen);
}

function moveLeftBoundary(delta) {
  if (window.matchMedia("(max-width: 60rem)").matches) return;
  const pairShare = layoutState.sidebar + centerShare();
  const minimumSidebar = measureCompactSidebarShare();
  layoutState.sidebar = clamp(layoutState.sidebar + delta, minimumSidebar, pairShare - 34);
  renderLayout();
  saveLayoutState();
}

function moveRightBoundary(delta) {
  if (!layoutState.previewOpen || window.matchMedia("(max-width: 60rem)").matches) return;
  const pairShare = centerShare() + layoutState.preview;
  layoutState.preview = clamp(layoutState.preview - delta, 20, Math.min(44, pairShare - 34));
  renderLayout();
  saveLayoutState();
}

function setupBoundary(handle, mover, reset) {
  let lastX = 0;
  handle.addEventListener("pointerdown", (event) => {
    lastX = event.clientX;
    handle.setPointerCapture(event.pointerId);
    handle.classList.add("dragging");
  });
  handle.addEventListener("pointermove", (event) => {
    if (!handle.hasPointerCapture(event.pointerId)) return;
    const delta = ((event.clientX - lastX) / $("appWorkspace").clientWidth) * 100;
    lastX = event.clientX;
    mover(delta);
  });
  const finish = (event) => {
    if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId);
    handle.classList.remove("dragging");
  };
  handle.addEventListener("pointerup", finish);
  handle.addEventListener("pointercancel", finish);
  handle.addEventListener("dblclick", reset);
  handle.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    mover(event.key === "ArrowLeft" ? -1 : 1);
  });
}

function setupResizableLayout() {
  if (!hasStoredLayout && window.matchMedia("(max-width: 60rem)").matches) layoutState.previewOpen = false;
  setupBoundary($("leftResizer"), moveLeftBoundary, () => {
    layoutState.sidebar = DEFAULT_LAYOUT.sidebar;
    renderLayout();
    saveLayoutState();
  });
  setupBoundary($("rightResizer"), moveRightBoundary, () => {
    layoutState.preview = DEFAULT_LAYOUT.preview;
    renderLayout();
    saveLayoutState();
  });
  window.addEventListener("resize", renderLayout);
  renderLayout();
}

function setPreviewOpen(open) {
  layoutState.previewOpen = Boolean(open);
  if (layoutState.previewOpen) {
    layoutState.sidebar = Math.min(layoutState.sidebar, CONTENT_SHARE - layoutState.preview - 34);
  }
  renderLayout();
  saveLayoutState();
}

function closeMobileSidebar() {
  $("appWorkspace").classList.remove("sidebar-open");
  $("sidebarToggle").setAttribute("aria-expanded", "false");
  renderLayout();
}

function setupShellControls() {
  $("previewToggle").onclick = () => setPreviewOpen(!layoutState.previewOpen);
  for (const button of document.querySelectorAll("[data-preview-close]")) button.onclick = () => setPreviewOpen(false);
  $("sidebarToggle").onclick = () => {
    const open = $("appWorkspace").classList.toggle("sidebar-open");
    if (open && layoutState.previewOpen) {
      layoutState.previewOpen = false;
      saveLayoutState();
    }
    $("sidebarToggle").setAttribute("aria-expanded", open ? "true" : "false");
    renderLayout();
  };
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if ($("notesDrawer").classList.contains("open")) setNotesDrawer(false);
    else closeMobileSidebar();
  });
}

function setNotesDrawer(open) {
  $("notesDrawer").classList.toggle("open", open);
  $("notesDrawer").setAttribute("aria-hidden", open ? "false" : "true");
  $("notesDrawer").toggleAttribute("inert", !open);
  if (open) window.setTimeout(() => $("noteTitle").focus(), 0);
  else $("notesToggle").focus();
}

function setRunState(label) {
  $("runStateText").textContent = label;
  document.querySelector(".run-state").classList.toggle("running", label !== "Idle");
}

function setBusy(busy) {
  requestBusy = busy;
  setRunState(busy ? "Running" : "Idle");
  for (const id of ["indexCourse", "sendQuestion", "generateSummary", "generateQuiz"]) {
    $(id).disabled = busy || !activeCourse;
  }
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 3200);
}

function escapeHtml(value) {
  return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

function setupActions() {
  $("saveRoot").onclick = () => saveRoot().catch((error) => showToast(error.message));
  $("refreshCourses").onclick = () => loadCourses().catch((error) => showToast(error.message));
  $("indexCourse").onclick = () => indexActiveCourse().catch((error) => showToast(error.message));
  $("sendQuestion").onclick = () => sendQuestion().catch((error) => showToast(error.message));
  $("question").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendQuestion().catch((error) => showToast(error.message));
    }
  });
  $("saveNote").onclick = () => saveNote().catch((error) => showToast(error.message));
  $("generateSummary").onclick = () => generateStudyArtifact("summary").catch((error) => showToast(error.message));
  $("generateQuiz").onclick = () => generateStudyArtifact("quiz").catch((error) => showToast(error.message));
  $("notesToggle").onclick = () => setNotesDrawer(true);
  $("notesClose").onclick = () => setNotesDrawer(false);
}

setupResizableLayout();
setupPreviewTabs();
setupFilePickers();
setupDragAndDrop();
setupShellControls();
setupActions();
loadConfig().then(loadCourses).catch((error) => {
  $("courseList").textContent = error.message;
});
