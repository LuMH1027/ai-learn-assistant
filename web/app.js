let courses = [];
let activeCourse = null;
let activeFile = null;
let pendingChatFiles = [];

const $ = (id) => document.getElementById(id);

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
  renderCourses();
}

function renderCourses() {
  const host = $("courseList");
  if (!courses.length) {
    host.className = "course-list empty";
    host.textContent = "未发现课程。请确认资料根目录下存在一级课程文件夹。";
    return;
  }
  host.className = "course-list";
  host.innerHTML = "";
  for (const course of courses) {
    const wrapper = document.createElement("div");
    wrapper.className = "course";
    const header = document.createElement("div");
    header.className = "course-header" + (activeCourse?.id === course.id ? " active" : "");
    header.tabIndex = 0;
    header.role = "button";
    header.setAttribute("aria-expanded", activeCourse?.id === course.id ? "true" : "false");
    header.innerHTML = `<span>${escapeHtml(course.name)}</span><span>${course.file_count} 个文件</span>`;
    header.onclick = () => selectCourse(course);
    header.onkeydown = (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectCourse(course);
      }
    };
    wrapper.appendChild(header);
    if (activeCourse?.id === course.id) {
      const tree = document.createElement("div");
      tree.className = "file-tree";
      tree.appendChild(renderNodes(course.children));
      wrapper.appendChild(tree);
    }
    host.appendChild(wrapper);
  }
}

function renderNodes(nodes) {
  const fragment = document.createDocumentFragment();
  for (const node of nodes) {
    const item = document.createElement("div");
    item.className = `tree-node ${node.type}`;
    item.textContent = node.type === "folder" ? `▾ ${node.name}` : `□ ${node.name}`;
    if (node.type === "file") {
      item.tabIndex = 0;
      item.role = "button";
      item.setAttribute("aria-label", `预览文件 ${node.name}`);
      item.onclick = () => previewFile(node);
      item.onkeydown = (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          previewFile(node);
        }
      };
    }
    fragment.appendChild(item);
    if (node.type === "folder") {
      const children = document.createElement("div");
      children.className = "tree-children";
      children.appendChild(renderNodes(node.children || []));
      fragment.appendChild(children);
    }
  }
  return fragment;
}

async function selectCourse(course) {
  activeCourse = course;
  $("agentTitle").textContent = `${course.name} Agent`;
  $("indexCourse").disabled = false;
  $("sendQuestion").disabled = false;
  $("saveNote").disabled = false;
  $("notesToggle").disabled = false;
  $("generateSummary").disabled = false;
  $("generateQuiz").disabled = false;
  $("courseDropZone").classList.add("ready");
  $("courseDropZone").textContent = `拖文件到这里，加入「${course.name}」课程资料`;
  renderCourses();
  await loadMessages();
  await loadNotes();
}

async function previewFile(file) {
  activeFile = file;
  $("previewTitle").textContent = file.name;
  const url = `/api/files/preview?id=${encodeURIComponent(file.id)}`;
  if (file.extension === ".pdf") {
    window.open(url, `preview-${file.id}`, "width=980,height=760");
    $("preview").innerHTML = `<div class="preview-empty">已打开 PDF 预览窗口：${escapeHtml(file.name)}<br>如果浏览器拦截弹窗，请允许本地页面打开新窗口。</div>`;
    return;
  }
  if ([".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"].includes(file.extension)) {
    $("preview").innerHTML = `<div class="image-preview-wrap"><img class="image-preview" src="${url}" alt="${escapeHtml(file.name)}" /></div>`;
    return;
  }
  const text = await fetch(url).then((res) => res.text());
  $("preview").innerHTML = `<pre class="text-preview">${escapeHtml(text)}</pre>`;
}

async function loadMessages() {
  if (!activeCourse) return;
  const data = await api(`/api/courses/${activeCourse.id}/messages`);
  renderMessages(data.messages);
}

async function loadNotes() {
  if (!activeCourse) return;
  const data = await api(`/api/courses/${activeCourse.id}/notes`);
  const host = $("notesList");
  host.innerHTML = "";
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
  host.innerHTML = "";
  if (!messages.length) {
    host.innerHTML = `<div class="message-empty">这是「${escapeHtml(activeCourse?.name || "当前课程")}」的独立聊天框。提问后，聊天记录会保存到本地文件。</div>`;
    return;
  }
  for (const message of messages) {
    appendMessage(message.role, message.content, message.citations || [], message.trace || []);
  }
  host.scrollTop = host.scrollHeight;
}

function appendMessage(role, content, citations = [], trace = []) {
  const node = document.createElement("div");
  node.className = `message ${role}`;
  node.textContent = content;
  if (trace.length) {
    node.appendChild(renderTrace(trace));
  }
  for (const citation of citations) {
    const link = document.createElement("span");
    link.className = "citation";
    link.textContent = `来源：${citation.file_name}${citation.page ? ` 第 ${citation.page} 页` : ""}，片段 ${citation.chunk_index}`;
    link.onclick = () => previewByFileId(citation.file_id);
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

function previewByFileId(fileId) {
  const file = findFile(courses, fileId);
  if (file) previewFile(file);
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
  await api("/api/config", {
    method: "POST",
    body: JSON.stringify(readSettings()),
  });
  activeCourse = null;
  await loadCourses();
}

function readSettings() {
  return {
    root_folder: $("rootFolder").value,
  };
}

async function indexActiveCourse() {
  if (!activeCourse) return;
  $("indexCourse").disabled = true;
  $("indexCourse").textContent = "入库中...";
  try {
    const data = await api(`/api/courses/${activeCourse.id}/index`, { method: "POST" });
    showToast(`知识库构建完成：${data.indexed_files} 个文件，${data.total_chunks} 个片段`);
  } finally {
    $("indexCourse").disabled = false;
    $("indexCourse").textContent = "构建知识库";
  }
}

async function sendQuestion() {
  if (!activeCourse) return;
  const question = $("question").value.trim();
  if (!question && !pendingChatFiles.length) return;
  $("question").value = "";
  setRunState("Running");
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
    setRunState("Idle");
  }
}

async function generateStudyArtifact(type) {
  if (!activeCourse) return;
  const path = type === "summary" ? "summary" : "quiz";
  const label = type === "summary" ? "课程摘要" : "练习题";
  setRunState("Running");
  try {
    const data = await api(`/api/courses/${activeCourse.id}/${path}`, { method: "POST" });
    if (data.courses) {
      courses = data.courses;
      activeCourse = courses.find((course) => course.id === activeCourse.id) || activeCourse;
      renderCourses();
    }
    await loadMessages();
    showToast(`${label}已保存到课程资料：${data.artifact?.name || "AI生成"}`);
  } finally {
    setRunState("Idle");
  }
}

async function saveNote() {
  if (!activeCourse) return;
  const title = $("noteTitle").value.trim() || "学习笔记";
  const content = $("noteContent").value.trim();
  if (!content) return;
  await api(`/api/courses/${activeCourse.id}/notes`, {
    method: "POST",
    body: JSON.stringify({ title, content }),
  });
  $("noteTitle").value = "";
  $("noteContent").value = "";
  await loadNotes();
  showToast("笔记已保存到当前课程。");
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 3200);
}

function setRunState(label) {
  $("runStateText").textContent = label;
  document.querySelector(".run-state").classList.toggle("running", label !== "Idle");
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
  showToast(`已加入课程资料：${data.saved.map((item) => item.name).join("、")}`);
  await loadCourses();
  activeCourse = data.courses.find((course) => course.id === activeCourse.id) || activeCourse;
  renderCourses();
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
    uploadCourseFiles([...event.dataTransfer.files]).catch((err) => showToast(err.message));
  });

  const composer = document.querySelector(".composer");
  composer.addEventListener("dragover", (event) => {
    event.preventDefault();
    $("chatDropHint").classList.add("show");
    composer.classList.add("dragging");
  });
  composer.addEventListener("dragleave", () => hideChatDropState());
  composer.addEventListener("drop", (event) => {
    event.preventDefault();
    pendingChatFiles = [...event.dataTransfer.files];
    composer.classList.remove("dragging");
    $("chatDropHint").classList.add("show");
    $("chatDropHint").textContent = `已附加 ${pendingChatFiles.length} 个文件，点击发送后 AI 会读取。`;
  });
}

function hideChatDropState() {
  document.querySelector(".composer").classList.remove("dragging");
  $("chatDropHint").classList.remove("show");
  $("chatDropHint").textContent = "松开后作为聊天附件读取，不写入课程目录";
}

function setNotesDrawer(open) {
  $("notesDrawer").classList.toggle("open", open);
  $("notesDrawer").setAttribute("aria-hidden", open ? "false" : "true");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

$("saveRoot").onclick = () => saveRoot().catch((err) => alert(err.message));
$("refreshCourses").onclick = () => loadCourses().catch((err) => alert(err.message));
$("indexCourse").onclick = () => indexActiveCourse().catch((err) => alert(err.message));
$("sendQuestion").onclick = () => sendQuestion().catch((err) => alert(err.message));
$("saveNote").onclick = () => saveNote().catch((err) => alert(err.message));
$("generateSummary").onclick = () => generateStudyArtifact("summary").catch((err) => alert(err.message));
$("generateQuiz").onclick = () => generateStudyArtifact("quiz").catch((err) => alert(err.message));
$("notesToggle").onclick = () => setNotesDrawer(true);
$("notesClose").onclick = () => setNotesDrawer(false);

loadConfig()
  .then(loadCourses)
  .then(setupDragAndDrop)
  .catch((err) => {
    $("courseList").textContent = err.message;
  });
