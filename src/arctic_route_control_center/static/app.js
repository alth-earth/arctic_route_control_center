"use strict";

const state = { system: null, catalog: null, artifacts: null, jobs: [] };
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: options.body ? { "Content-Type": "application/json", ...(options.headers || {}) } : options.headers,
  });
  const payload = await response.json().catch(() => ({ error: `HTTP ${response.status}` }));
  if (!response.ok || payload.ok === false) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function toast(message, isError = false) {
  const node = $("#toast");
  node.textContent = message;
  node.style.borderColor = isError ? "var(--red)" : "var(--ice)";
  node.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove("show"), 3600);
}

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function showPage(name) {
  $$(".page").forEach((node) => node.classList.toggle("active", node.id === `page-${name}`));
  $$(".nav-item").forEach((node) => node.classList.toggle("active", node.dataset.page === name));
}

function bindHelpDialog() {
  const dialog = $("#help-dialog");
  const opener = $("#help-button");
  const closer = $("#help-close");
  const close = () => {
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  };
  opener.onclick = () => {
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  };
  closer.onclick = close;
  dialog.addEventListener("cancel", (event) => { event.preventDefault(); close(); });
  dialog.addEventListener("click", (event) => { if (event.target === dialog) close(); });
}

async function loadCore() {
  const [system, catalog, settings] = await Promise.all([
    api("/api/system"), api("/api/catalog"), api("/api/settings"),
  ]);
  state.system = system;
  state.catalog = catalog;
  renderSystem();
  renderCatalogControls();
  renderSettings(settings.settings);
}

function renderSystem() {
  const grid = $("#module-grid");
  grid.replaceChildren();
  state.system.packages.forEach((item) => {
    const card = element("article", undefined, "card");
    card.append(element("div", item.package, "label"), element("div", item.version, "value"));
    card.append(element("span", item.status, `badge ${item.status === "available" ? "ready" : "incomplete"}`));
    grid.append(card);
  });
  const paths = $("#path-list");
  paths.replaceChildren();
  Object.entries(state.system.paths).forEach(([key, value]) => {
    paths.append(element("dt", key), element("dd", value));
  });
}

function renderCatalogControls() {
  const scenarios = state.catalog.contracts.release_scenario_ids;
  $$('[data-scenarios]').forEach((select) => {
    select.replaceChildren(...scenarios.map((id) => new Option(id, id)));
  });
  const corridors = Object.keys(state.catalog.contracts.corridors);
  $$('[data-corridors]').forEach((select) => {
    select.replaceChildren(...corridors.map((id) => new Option(id, id)));
  });
  renderContractIds();
  const sources = $("#source-options");
  sources.replaceChildren(...state.catalog.data.network_sources.map((name) => checkbox(name, name, true)));
  $("#type-count").textContent = `正式数据类别（${state.catalog.data.required_count} 必需 + ${state.catalog.data.optional_count} 可选；A 共注册 ${state.catalog.data.count} 类）`;
  const typeNodes = state.catalog.data.data_types.map((item) => {
    const formal = ["required", "optional"].includes(item.release_role);
    const label = checkbox(item.name, item.name, item.release_role === "required");
    const input = $("input", label); input.disabled = !formal;
    label.append(element("small", `${item.release_role} · ${item.category} · ${item.source_family}`));
    return label;
  });
  $("#type-options").replaceChildren(...typeNodes.map((node) => node.cloneNode(true)));
  $("#bundle-types").replaceChildren(...typeNodes.map((node) => node.cloneNode(true)));
  const carraTypes = state.catalog.data.independent_acquisition_sources.carra.data_types;
  $("#carra-type-options").replaceChildren(
    ...carraTypes.map((name) => checkbox(name, name, true))
  );
}

function checkbox(value, labelText, checked) {
  const label = document.createElement("label");
  const input = document.createElement("input");
  input.type = "checkbox"; input.value = value; input.checked = checked;
  label.append(input, element("span", labelText));
  return label;
}

function renderContractIds() {
  if (!state.catalog) return;
  const kind = $("#contract-kind").value;
  const ids = Object.keys(state.catalog.contracts[kind]);
  $("#contract-id").replaceChildren(...ids.map((id) => new Option(id, id)));
}

function formObject(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function checkedValues(container) {
  return $$("input[type=checkbox]:checked", container).map((node) => node.value);
}

async function startJob(operation, parameters) {
  const result = await api("/api/jobs", { method: "POST", body: JSON.stringify({ operation, parameters }) });
  toast(`任务已启动：${result.job.job_id}`);
  showPage("jobs");
  await loadJobs();
}

async function loadArtifacts() {
  const payload = await api("/api/artifacts");
  state.artifacts = payload;
  const root = $("#artifact-list"); root.replaceChildren();
  payload.packages.forEach((item) => {
    const row = element("article", undefined, "list-item");
    const content = document.createElement("div");
    const title = element("h3", item.display_name || item.package_dir);
    const badge = element("span", item.status, `badge ${item.status}`); title.append(" ", badge);
    content.append(title, element("p", `${item.scenario_id || "未知场景"} · routes=${item.route_count || 0} · ${item.reason || "校验通过"}`));
    const actions = element("div", undefined, "list-actions");
    const isRootPackage = item.bundle_path === "bundle.json";
    if (isRootPackage || (item.status === "ready" && item.location !== "inbox")) {
      const link = element("a", "在 Viewer 打开", "button");
      if (isRootPackage) {
        link.href = "/viewer/";
      } else {
        const params = new URLSearchParams({ package: item.package_dir });
        if (item.location === "embedded" || item.location === "ready") {
          params.set("package_location", item.location);
        }
        link.href = `/viewer/?${params.toString()}`;
      }
      link.target = "_blank"; link.rel = "noreferrer"; actions.append(link);
    }
    if (item.location === "inbox" && item.status === "ready") {
      const button = element("button", "提升为 ready", "button primary");
      button.onclick = async () => {
        try { await api("/api/artifacts/promote", { method: "POST", body: JSON.stringify({ package_name: item.package_dir }) }); toast("制品已发布"); await loadArtifacts(); }
        catch (error) { toast(error.message, true); }
      };
      actions.append(button);
    }
    row.append(content, actions); root.append(row);
  });
}

async function loadJobs() {
  const payload = await api("/api/jobs"); state.jobs = payload.jobs;
  const root = $("#job-list"); root.replaceChildren();
  if (!state.jobs.length) root.append(element("p", "尚无任务。", "hint"));
  state.jobs.forEach((job) => {
    const row = element("article", undefined, "list-item");
    const content = document.createElement("div");
    const title = element("h3", `${job.operation} · ${job.job_id}`);
    title.append(" ", element("span", job.status, `badge ${job.status}`));
    content.append(title, element("p", `${job.created_at} · ${job.message} · ${job.output_dir}`));
    if (job.carra_progress) {
      const progress = job.carra_progress;
      content.append(element("p", `预计周期 ${progress.estimated_cycles} · 已复用 ${progress.cache_hits ?? 0} · 已下载 ${progress.downloaded_cycles ?? 0} · 已发布 ${progress.frames_published ?? 0}`, "hint"));
    }
    const actions = element("div", undefined, "list-actions");
    const view = element("button", "查看日志", "button");
    view.onclick = () => showJob(job.job_id); actions.append(view);
    if (["queued", "running"].includes(job.status)) {
      const cancel = element("button", "取消", "button danger");
      cancel.onclick = async () => { try { await api(`/api/jobs/${job.job_id}/cancel`, { method: "POST", body: "{}" }); await loadJobs(); } catch (error) { toast(error.message, true); } };
      actions.append(cancel);
    }
    row.append(content, actions); root.append(row);
  });
}

async function showJob(id) {
  try { const payload = await api(`/api/jobs/${id}`); $("#job-log").textContent = payload.job.log_tail || "日志为空。"; }
  catch (error) { toast(error.message, true); }
}

function renderSettings(settings) {
  $("#settings-form").elements.copernicus_env_file.value = settings.credentials.copernicus_env_file || "";
  $("#settings-form").elements.cdsapi_rc_file.value = settings.credentials.cdsapi_rc_file || "";
}

function bindForms() {
  $("#acquire-form").onsubmit = async (event) => {
    event.preventDefault(); const values = formObject(event.currentTarget);
    values.sources = checkedValues($("#source-options")); values.types = checkedValues($("#type-options"));
    if (values.candidate_route_distance_nm) values.candidate_route_distance_nm = Number(values.candidate_route_distance_nm);
    try { await startJob("a_acquire", values); } catch (error) { toast(error.message, true); }
  };
  $("#bundle-form").onsubmit = async (event) => {
    event.preventDefault(); const values = formObject(event.currentTarget); values.types = checkedValues($("#bundle-types"));
    try { await startJob("a_bundle", values); } catch (error) { toast(error.message, true); }
  };
  $("#carra-form").onsubmit = async (event) => {
    event.preventDefault(); const values = formObject(event.currentTarget);
    values.types = checkedValues($("#carra-type-options"));
    try { await startJob("a_carra_acquire", values); } catch (error) { toast(error.message, true); }
  };
  $("#orchestrator-form").onsubmit = async (event) => {
    event.preventDefault(); const values = formObject(event.currentTarget);
    values.planning_workers = Number(values.planning_workers); values.stage_timeout_seconds = Number(values.stage_timeout_seconds);
    try { await startJob("orchestrator_run", values); } catch (error) { toast(error.message, true); }
  };
  $("#publish-form").onsubmit = async (event) => {
    event.preventDefault(); const values = formObject(event.currentTarget);
    values.route_motion_sets = values.route_motion_sets ? values.route_motion_sets.split(",").map((x) => x.trim()).filter(Boolean) : [];
    values.route_motion_candidate_sets = values.route_motion_candidate_sets ? values.route_motion_candidate_sets.split(",").map((x) => x.trim()).filter(Boolean) : [];
    try { await startJob("publish_viewer", values); } catch (error) { toast(error.message, true); }
  };
  $("#settings-form").onsubmit = async (event) => {
    event.preventDefault();
    const copernicus = event.currentTarget.elements.copernicus_env_file.value.trim();
    const cdsapi = event.currentTarget.elements.cdsapi_rc_file.value.trim();
    try { const payload = await api("/api/settings", { method: "POST", body: JSON.stringify({ schema_version: "arctic-route-control-center.config.v1", credentials: { copernicus_env_file: copernicus, cdsapi_rc_file: cdsapi } }) }); renderSettings(payload.settings); toast("设置已保存"); }
    catch (error) { toast(error.message, true); }
  };
}

async function refresh() {
  try { await Promise.all([loadArtifacts(), loadJobs()]); } catch (error) { toast(error.message, true); }
}

async function init() {
  $$(".nav-item").forEach((node) => node.onclick = () => showPage(node.dataset.page));
  $$('[data-refresh]').forEach((node) => node.onclick = refresh);
  bindHelpDialog();
  $("#contract-kind").onchange = renderContractIds;
  $("#show-contract").onclick = () => {
    const kind = $("#contract-kind").value; const id = $("#contract-id").value;
    $("#contract-detail").textContent = JSON.stringify(state.catalog.contracts[kind][id], null, 2);
  };
  bindForms();
  try {
    await api("/api/health"); $("#health").textContent = "后端已连接"; $("#health").className = "badge ready";
    await loadCore(); await refresh();
  } catch (error) {
    $("#health").textContent = "后端不可用"; $("#health").className = "badge failed"; toast(error.message, true);
  }
  setInterval(() => { if ($("#page-jobs").classList.contains("active")) loadJobs().catch(() => {}); }, 3000);
}

init();
