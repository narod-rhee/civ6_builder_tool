const form = document.querySelector("#cropperForm");
const imageInput = document.querySelector("#imageInput");
const fileName = document.querySelector("#fileName");
const previewImage = document.querySelector("#previewImage");
const statusBox = document.querySelector("#status");
const modeSelect = document.querySelector("#mode");
const profileInfo = document.querySelector("#profileInfo");
const filesBox = document.querySelector("#files");
const warningsBox = document.querySelector("#warnings");
const generateButton = document.querySelector("#generateButton");
const idManifestInput = document.querySelector("#idManifestInput");
const idManifestSelect = document.querySelector("#idManifestSelect");
const templateForm = document.querySelector("#templateForm");
const templateFilesBox = document.querySelector("#templateFiles");
const templateOutputs = document.querySelector("#templateOutputs");
const templateRoot = document.querySelector("#templateRoot");
const templateStatus = document.querySelector("#templateStatus");
const replacementMap = document.querySelector("#replacementMap");
const selectAllTemplates = document.querySelector("#selectAllTemplates");
const clearTemplates = document.querySelector("#clearTemplates");
const templateUpload = document.querySelector("#templateUpload");
const copilotPrefillInput = document.querySelector("#copilotPrefillInput");
const civCount = document.querySelector("#civCount");
const leaderCount = document.querySelector("#leaderCount");
const civEntityGrid = document.querySelector("#civEntityGrid");
const leaderEntityGrid = document.querySelector("#leaderEntityGrid");
const extractorForm = document.querySelector("#extractorForm");
const extractorSourcePath = document.querySelector("#extractorSourcePath");
const extractorProfileOut = document.querySelector("#extractorProfileOut");
const extractorPrefillOut = document.querySelector("#extractorPrefillOut");
const extractXmlButton = document.querySelector("#extractXmlButton");
const summarizeXmlButton = document.querySelector("#summarizeXmlButton");
const buildPrefillButton = document.querySelector("#buildPrefillButton");
const extractorStatus = document.querySelector("#extractorStatus");
const extractorLinks = document.querySelector("#extractorLinks");
const extractorSummary = document.querySelector("#extractorSummary");
const extractorJson = document.querySelector("#extractorJson");
const imagePromptForm = document.querySelector("#imagePromptForm");
const assetType = document.querySelector("#assetType");
const imagePromptStatus = document.querySelector("#imagePromptStatus");
const novelPositive = document.querySelector("#novelPositive");
const novelNegative = document.querySelector("#novelNegative");
const novelSettings = document.querySelector("#novelSettings");
const openaiImagePrompt = document.querySelector("#openaiImagePrompt");
const copyNovelPrompt = document.querySelector("#copyNovelPrompt");
const copyOpenAIPrompt = document.querySelector("#copyOpenAIPrompt");
const createOpenAIImage = document.querySelector("#createOpenAIImage");
const openaiImageOutputs = document.querySelector("#openaiImageOutputs");

const refs = {
  toolMessage: document.querySelector("#toolMessage"),
  pageButtons: document.querySelectorAll("[data-page]"),
  pagePanels: document.querySelectorAll("[data-page-panel]"),
  statusPill: document.querySelector("#statusPill"),
  workflowId: document.querySelector("#workflowId"),
  workflowVersion: document.querySelector("#workflowVersion"),
  chatUser: document.querySelector("#chatUser"),
  sessionId: document.querySelector("#sessionId"),
  workspaceName: document.querySelector("#workspaceName"),
  workspacePath: document.querySelector("#workspacePath"),
  fileCount: document.querySelector("#fileCount"),
  fileList: document.querySelector("#workspaceFiles"),
  eventLine: document.querySelector("#eventLine"),
  chatFrame: document.querySelector("#chatFrame"),
  emptyState: document.querySelector("#emptyState"),
  connectButton: document.querySelector("#connectButton"),
  newSessionButton: document.querySelector("#newSessionButton"),
  focusButton: document.querySelector("#focusButton"),
  themeToggle: document.querySelector("#themeToggle"),
  serverPoolCount: document.querySelector("#serverPoolCount"),
  startServerPool: document.querySelector("#startServerPool"),
  serverPoolStatus: document.querySelector("#serverPoolStatus"),
  serverPoolLinks: document.querySelector("#serverPoolLinks"),
};

const state = {
  config: null,
  chatkit: null,
  session: null,
  connecting: false,
  theme: localStorage.getItem("cropper-theme") || "light",
  templates: [],
  uploadedTemplates: [],
  autoSelectedTemplatePaths: new Set(),
  cropperIdOptions: [],
  assetPresets: {},
  openaiImageConfig: {},
};

let profiles = {};
let previewObjectUrl = "";

init();

async function init() {
  applyTheme(state.theme);
  renderEntityInputs();
  switchPage("cropper");
  await Promise.all([loadProfiles(), loadConfig(), loadTemplates(), loadAssetPresets()]);
  await loadServerPool();
}

async function loadProfiles() {
  const response = await fetch("/api/profiles");
  const payload = await response.json();
  profiles = payload.profiles;
  modeSelect.replaceChildren();
  for (const [mode, profile] of Object.entries(profiles)) {
    const option = document.createElement("option");
    option.value = mode;
    option.textContent = profile.label;
    modeSelect.append(option);
  }
  modeSelect.value = "civilization_icons";
  updateProfileInfo();
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || payload.message || `Request failed: ${response.status}`);
  }
  return payload;
}

async function loadConfig() {
  state.config = await fetchJson("/api/config");
  renderConfig();
}

function renderConfig() {
  const config = state.config;
  refs.workflowId.textContent = config.workflow_id || "Missing";
  refs.workflowVersion.textContent = config.workflow_version || "latest";
  refs.chatUser.textContent = config.user || "-";
  refs.workspaceName.textContent = config.workspace_name || "Workspace";
  refs.workspacePath.textContent = config.workspace_path || "-";
  refs.fileCount.textContent = `${config.file_count || 0} files`;

  refs.fileList.replaceChildren();
  for (const file of config.files || []) {
    const item = document.createElement("li");
    item.textContent = file;
    item.title = file;
    refs.fileList.appendChild(item);
  }

  if (!config.has_api_key || !config.workflow_id) {
    setAgentStatus("Config", "error");
    setEvent("Add OPENAI_API_KEY and AGENT_WORKFLOW_ID to .env to enable the agent.");
  } else {
    setAgentStatus("Ready");
    setEvent("Agent ready");
  }
}

async function loadServerPool() {
  try {
    const payload = await fetchJson("/api/server-pool");
    renderServerPool(payload);
  } catch (error) {
    refs.serverPoolStatus.textContent = error.message;
  }
}

async function startServerPool() {
  const count = Number.parseInt(refs.serverPoolCount.value, 10) || 2;
  refs.serverPoolStatus.textContent = "Starting sibling servers...";
  refs.startServerPool.disabled = true;
  try {
    const payload = await fetchJson("/api/server-pool/start", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({count}),
    });
    renderServerPool(payload.pool || payload);
    refs.serverPoolStatus.textContent = `Started ${payload.launched?.length || 0} server(s).`;
  } catch (error) {
    refs.serverPoolStatus.textContent = error.message;
  } finally {
    refs.startServerPool.disabled = false;
  }
}

function renderServerPool(payload) {
  refs.serverPoolLinks.replaceChildren();
  const current = payload.current;
  if (current) {
    refs.serverPoolStatus.textContent = `Current server: ${current.url}`;
  }
  for (const server of payload.members || []) {
    const item = document.createElement("div");
    const link = document.createElement("a");
    link.href = server.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = `Server ${server.port}`;
    const meta = document.createElement("span");
    meta.textContent = `PID ${server.pid}`;
    item.append(link, meta);
    refs.serverPoolLinks.append(item);
  }
}

async function waitForChatKit() {
  if (!window.customElements) {
    throw new Error("This browser does not support web components.");
  }
  await customElements.whenDefined("openai-chatkit");
}

async function getClientSecret(currentClientSecret) {
  setAgentStatus(currentClientSecret ? "Refreshing" : "Creating", "busy");
  const session = await fetchJson("/api/chatkit/session", { method: "POST" });
  state.session = session;
  refs.sessionId.textContent = session.id || "-";
  setAgentStatus("Connected");
  setEvent(currentClientSecret ? "Session refreshed" : "Session created");
  return session.client_secret;
}

function buildChatKitOptions() {
  return {
    api: {
      getClientSecret,
    },
    frameTitle: "Icon Forge Agent",
    initialThread: null,
    locale: navigator.language || "en",
    theme: state.theme,
    onClientTool: async ({ name, params }) => {
      if (name === "get_workspace_context") {
        return {
          workspace: state.config,
          cropper: {
            selected_profile: modeSelect.value,
            profile: profiles[modeSelect.value],
            base_name: form.elements.base_name.value,
            output_dir: form.elements.output_dir.value,
            subject_scale_percent: form.elements.subject_scale_percent.value,
            vertical_offset_percent: form.elements.vertical_offset_percent.value,
            horizontal_offset_percent: form.elements.horizontal_offset_percent.value,
            background_method: form.elements.background_method.value,
          },
          params,
        };
      }

      return {
        error: `No browser client tool named ${name} is registered.`,
      };
    },
  };
}

function addChatKitEvents(chatkit) {
  chatkit.addEventListener("chatkit.error", (event) => {
    const detail = event.detail || {};
    setAgentStatus("Error", "error");
    setEvent(detail.error?.message || "ChatKit error");
  });

  chatkit.addEventListener("chatkit.response.start", () => {
    setAgentStatus("Responding", "busy");
    setEvent("Response streaming");
  });

  chatkit.addEventListener("chatkit.response.end", () => {
    setAgentStatus("Connected");
    setEvent("Response complete");
  });

  chatkit.addEventListener("chatkit.thread.change", (event) => {
    const threadId = event.detail?.threadId;
    setEvent(threadId ? `Thread ${threadId}` : "New thread");
  });
}

async function mountChatKit() {
  if (state.connecting) {
    return;
  }

  state.connecting = true;
  refs.connectButton.disabled = true;
  refs.newSessionButton.disabled = true;

  try {
    await waitForChatKit();

    if (state.chatkit) {
      state.chatkit.remove();
      state.chatkit = null;
    }

    refs.emptyState.hidden = true;
    const chatkit = document.createElement("openai-chatkit");
    chatkit.className = "chatkitPanel";
    chatkit.setOptions(buildChatKitOptions());
    addChatKitEvents(chatkit);
    refs.chatFrame.appendChild(chatkit);
    state.chatkit = chatkit;
    setEvent("Chat mounted");
  } catch (error) {
    refs.emptyState.hidden = false;
    setAgentStatus("Error", "error");
    setEvent(error.message);
  } finally {
    state.connecting = false;
    refs.connectButton.disabled = false;
    refs.newSessionButton.disabled = false;
  }
}

async function sendStarter(text) {
  if (!state.chatkit) {
    await mountChatKit();
  }

  if (!state.chatkit) {
    return;
  }

  if (typeof state.chatkit.sendUserMessage === "function") {
    await state.chatkit.sendUserMessage({ text });
    return;
  }

  if (typeof state.chatkit.setComposerValue === "function") {
    state.chatkit.setComposerValue(text);
    state.chatkit.focusComposer?.();
  }
}

imageInput.addEventListener("change", () => {
  const file = imageInput.files[0];
  fileName.textContent = file ? file.name : "No file selected";
  if (previewObjectUrl) {
    URL.revokeObjectURL(previewObjectUrl);
    previewObjectUrl = "";
  }
  if (file) {
    previewObjectUrl = URL.createObjectURL(file);
    previewImage.src = previewObjectUrl;
    previewImage.style.display = "block";
  } else {
    previewImage.removeAttribute("src");
    previewImage.style.display = "none";
  }
});

idManifestInput.addEventListener("change", handleIdManifestLoad);
idManifestSelect.addEventListener("change", applySelectedIdManifestTarget);
modeSelect.addEventListener("change", updateProfileInfo);
refs.themeToggle.addEventListener("click", () => applyTheme(state.theme === "dark" ? "light" : "dark"));
refs.connectButton.addEventListener("click", mountChatKit);
refs.newSessionButton.addEventListener("click", mountChatKit);
refs.focusButton.addEventListener("click", () => state.chatkit?.focusComposer?.());
refs.startServerPool.addEventListener("click", startServerPool);

refs.pageButtons.forEach((button) => {
  button.addEventListener("click", () => switchPage(button.dataset.page));
});

templateForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await generateTemplates();
});

selectAllTemplates.addEventListener("click", () => setTemplateSelection(true));
clearTemplates.addEventListener("click", () => setTemplateSelection(false));
templateUpload.addEventListener("change", handleTemplateUpload);
copilotPrefillInput.addEventListener("change", handleCopilotPrefillLoad);
civCount.addEventListener("change", renderEntityInputs);
leaderCount.addEventListener("change", renderEntityInputs);
extractXmlButton.addEventListener("click", extractXmlProfile);
summarizeXmlButton.addEventListener("click", summarizeXmlProfile);
buildPrefillButton.addEventListener("click", buildCopilotPrefillFromProfile);
civEntityGrid.addEventListener("input", (event) => {
  if (event.target.matches("[data-civ-name]")) {
    refreshCivilizationDerivedIds();
    refreshLeaderCivilizationOptions();
  }
  if (event.target.matches("input, textarea, select")) {
    updateAutoTemplateSelection();
  }
});
civEntityGrid.addEventListener("change", (event) => {
  if (event.target.matches("[data-enable-uniques], [data-enable-governors]")) {
    toggleUniquePanel(event.target.closest("[data-civ-card]"));
    updateAutoTemplateSelection();
  }
});
leaderEntityGrid.addEventListener("input", (event) => {
  if (event.target.matches("[data-leader-name]")) {
    refreshLeaderDerivedIds();
  }
  if (event.target.matches("input, textarea, select")) {
    updateAutoTemplateSelection();
  }
});

imagePromptForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await generateNovelPrompt();
});

assetType.addEventListener("change", applyAssetPreset);
copyNovelPrompt.addEventListener("click", () => copyText(novelPositive.value));
copyOpenAIPrompt.addEventListener("click", () => copyText(openaiImagePrompt.value));
createOpenAIImage.addEventListener("click", createOpenAIAsset);

document.querySelectorAll("[data-preset]").forEach((button) => {
  button.addEventListener("click", () => applyPreset(button.dataset.preset));
});

document.querySelectorAll("[data-template-filter]").forEach((button) => {
  button.addEventListener("click", () => selectTemplateGroup(button.dataset.templateFilter));
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => sendStarter(button.dataset.prompt));
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const action = cropperActionForMode(modeSelect.value);
  await submitForm(action.endpoint, action.busyText);
});

function updateProfileInfo() {
  const profile = profiles[modeSelect.value];
  if (!profile) {
    profileInfo.textContent = "";
    return;
  }
  const sizeText = profile.sizes && profile.sizes.length
    ? `Sizes: ${profile.sizes.join(", ")}.`
    : `Dimensions: ${(profile.dimensions || []).map((item) => `${item[0]}x${item[1]}`).join(", ")}.`;
  profileInfo.textContent = `${profile.notes} ${sizeText} Shape: ${profile.shape}.`;
  generateButton.textContent = cropperActionForMode(modeSelect.value).label;
  const rightScale = form.elements.unit_right_scale_percent;
  if (modeSelect.value === "unit_icons" && rightScale.value === "100") {
    rightScale.value = form.elements.subject_scale_percent.value || "100";
  }
  const baseName = form.elements.base_name;
  if (modeSelect.value === "unit_icons" && baseName.value === "ICON_CUSTOM") {
    baseName.value = "TemplateUnitAtlas";
  }
  if (modeSelect.value === "diplomacy_backgrounds" && ["ICON_CUSTOM", "TemplateUnitAtlas"].includes(baseName.value)) {
    baseName.value = "DIPLOBG_CUSTOM";
  }
  if (modeSelect.value === "moment_pictures" && ["ICON_CUSTOM", "TemplateUnitAtlas", "DIPLOBG_CUSTOM"].includes(baseName.value)) {
    baseName.value = "MOMENT_CUSTOM";
  }
  if (modeSelect.value === "thumbnails" && ["ICON_CUSTOM", "TemplateUnitAtlas", "DIPLOBG_CUSTOM", "MOMENT_CUSTOM"].includes(baseName.value)) {
    baseName.value = "THUMBNAIL_CUSTOM";
  }
  if (modeSelect.value === "arx_icons" && ["ICON_CUSTOM", "TemplateUnitAtlas", "DIPLOBG_CUSTOM", "MOMENT_CUSTOM", "THUMBNAIL_CUSTOM"].includes(baseName.value)) {
    baseName.value = "ARX_CUSTOM";
  }
  if (modeSelect.value === "raw_256" && ["ICON_CUSTOM", "TemplateUnitAtlas", "DIPLOBG_CUSTOM", "MOMENT_CUSTOM", "THUMBNAIL_CUSTOM"].includes(baseName.value)) {
    baseName.value = "RAW_CUSTOM";
  }
  if (modeSelect.value === "background_removal" && ["ICON_CUSTOM", "TemplateUnitAtlas", "DIPLOBG_CUSTOM", "MOMENT_CUSTOM", "THUMBNAIL_CUSTOM", "RAW_CUSTOM"].includes(baseName.value)) {
    baseName.value = "BACKGROUND_CLEAN";
  }
  applyDefaultOutputDir(modeSelect.value);
}

function cropperActionForMode(mode) {
  if (mode === "raw_256") {
    return { endpoint: "/api/raw256", busyText: "Creating raw 256 PNG...", label: "Generate Raw 256" };
  }
  if (mode === "background_removal") {
    return { endpoint: "/api/remove-background", busyText: "Removing background...", label: "Remove Background" };
  }
  return { endpoint: "/api/generate", busyText: "Generating assets...", label: "Generate" };
}

function applyDefaultOutputDir(mode) {
  const output = form.elements.output_dir;
  const defaults = new Set([
    "output/frontend_icons",
    "output/diplomacy_backgrounds",
    "output/moment_pictures",
    "output/thumbnails",
    "output/arx_icons",
    "output/background_removed",
    "output/raw_256",
  ]);
  if (!defaults.has(output.value)) {
    return;
  }
  const next = {
    diplomacy_backgrounds: "output/diplomacy_backgrounds",
    moment_pictures: "output/moment_pictures",
    thumbnails: "output/thumbnails",
    arx_icons: "output/arx_icons",
    background_removal: "output/background_removed",
    raw_256: "output/raw_256",
  }[mode] || "output/frontend_icons";
  output.value = next;
}

async function submitForm(endpoint, busyText) {
  if (!imageInput.files.length) {
    setStatus("Choose an image first.");
    return;
  }

  setStatus(busyText);
  filesBox.replaceChildren();
  warningsBox.textContent = "";

  const data = new FormData(form);
  const response = await fetch(endpoint, { method: "POST", body: data });
  const payload = await response.json();
  if (!response.ok || payload.status === "error") {
    setStatus("Error");
    warningsBox.textContent = payload.message || "Something went wrong.";
    return;
  }

  renderResults(payload);
  setStatus(`Generated ${payload.generated_files.length} file(s).`);
}

function renderResults(payload) {
  warningsBox.textContent = payload.warnings?.length ? payload.warnings.join(" ") : "";
  filesBox.replaceChildren();

  for (const file of payload.generated_files) {
    const item = document.createElement("article");
    item.className = "fileItem";

    const img = document.createElement("img");
    img.src = file.url;
    img.alt = "";
    img.loading = "lazy";
    img.decoding = "async";

    const meta = document.createElement("div");
    meta.textContent = `${file.width}x${file.height}${file.variant ? ` (${file.variant})` : ""}`;

    const link = document.createElement("a");
    link.href = file.url;
    link.target = "_blank";
    link.textContent = file.path.split(/[\\/]/).pop();

    item.append(img, meta, link);
    filesBox.append(item);
  }
}

async function handleIdManifestLoad() {
  const file = idManifestInput.files?.[0];
  if (!file) {
    return;
  }
  try {
    const manifest = JSON.parse(await file.text());
    state.cropperIdOptions = buildCropperIdOptions(manifest);
    idManifestSelect.replaceChildren();
    if (!state.cropperIdOptions.length) {
      idManifestSelect.disabled = true;
      idManifestSelect.append(new Option("No cropper-ready IDs found", ""));
      setStatus("Template ID JSON loaded, but no cropper targets were found.");
      return;
    }
    idManifestSelect.disabled = false;
    idManifestSelect.append(new Option("Choose generated ID target", ""));
    state.cropperIdOptions.forEach((option, index) => {
      idManifestSelect.append(new Option(option.label, String(index)));
    });
    setStatus(`Loaded ${state.cropperIdOptions.length} saved ID target(s).`);
  } catch (error) {
    setStatus(`Could not load Template ID JSON: ${error.message}`);
  }
}

function buildCropperIdOptions(manifest) {
  const options = [];
  const addOption = (owner, target, cropperOption) => {
    if (!cropperOption?.mode || !cropperOption?.base_name) {
      return;
    }
    options.push({
      label: `${owner} - ${target.label || cropperOption.label || cropperOption.mode}`,
      mode: cropperOption.mode,
      baseName: cropperOption.base_name,
      outputDir: cropperOption.output_dir || "",
    });
  };
  for (const civ of manifest.civilizations || []) {
    const owner = civ.name || civ.id || "Civilization";
    for (const option of civ.cropper_options || []) {
      addOption(owner, {label: option.label}, option);
    }
    for (const unit of civ.units || []) {
      for (const option of unit.cropper_options || []) addOption(owner, unit, option);
    }
    for (const building of civ.buildings || []) {
      for (const option of building.cropper_options || []) addOption(owner, building, option);
    }
    for (const improvement of civ.improvements || []) {
      for (const option of improvement.cropper_options || []) addOption(owner, improvement, option);
    }
    for (const district of civ.districts || []) {
      for (const option of district.cropper_options || []) addOption(owner, district, option);
    }
    for (const governor of civ.governors || []) {
      for (const option of governor.cropper_options || []) addOption(owner, governor, option);
    }
  }
  for (const leader of manifest.leaders || []) {
    const owner = leader.name || leader.id || "Leader";
    for (const option of leader.cropper_options || []) {
      addOption(owner, {label: option.label}, option);
    }
  }
  return options;
}

function applySelectedIdManifestTarget() {
  const option = state.cropperIdOptions[Number.parseInt(idManifestSelect.value, 10)];
  if (!option) {
    return;
  }
  if (profiles[option.mode]) {
    modeSelect.value = option.mode;
  }
  form.elements.base_name.value = option.baseName;
  if (option.outputDir) {
    form.elements.output_dir.value = option.outputDir;
  }
  updateProfileInfo();
  form.elements.base_name.value = option.baseName;
  setStatus(`Loaded ${option.label}.`);
}

function setStatus(text) {
  statusBox.textContent = text;
}

function switchPage(page) {
  refs.pagePanels.forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.pagePanel === page);
  });
  refs.pageButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.page === page);
  });
  if (page === "agent") {
    refs.toolMessage.textContent = "Agent workspace";
    setStatus("Agent workspace");
  } else if (page === "templates") {
    refs.toolMessage.textContent = "Template Copilot";
    setStatus("Template Copilot");
  } else if (page === "extractor") {
    refs.toolMessage.textContent = "XML extractor";
    setStatus("XML extractor");
  } else if (page === "imageLab") {
    refs.toolMessage.textContent = "Image Lab";
    setStatus("Image Lab");
  } else {
    refs.toolMessage.textContent = "Cropper loading";
    setStatus("Cropper loading");
  }
}

async function loadAssetPresets() {
  try {
    const payload = await fetchJson("/api/asset-presets");
    state.assetPresets = payload.presets || {};
    state.openaiImageConfig = payload.openai || {};
    renderOpenAIModelOptions();
    assetType.replaceChildren();
    for (const [key, preset] of Object.entries(state.assetPresets)) {
      const option = document.createElement("option");
      option.value = key;
      option.textContent = preset.label || key;
      assetType.append(option);
    }
    applyAssetPreset();
  } catch (error) {
    imagePromptStatus.textContent = error.message;
  }
}

function renderOpenAIModelOptions() {
  const select = document.querySelector("#openaiImageModel");
  const models = state.openaiImageConfig.models || [];
  if (!models.length) {
    return;
  }
  const selected = state.openaiImageConfig.default_model || models[0];
  select.replaceChildren();
  for (const model of models) {
    const option = document.createElement("option");
    option.value = model;
    option.textContent = model;
    select.append(option);
  }
  select.value = models.includes(selected) ? selected : models[0];
}

function applyAssetPreset() {
  const preset = state.assetPresets[assetType.value];
  if (!preset) {
    return;
  }
  const promptEngine = preset.prompt_engine || "novelai";
  const openaiEnabled = preset.openai_enabled !== false;
  createOpenAIImage.disabled = !openaiEnabled;
  createOpenAIImage.title = openaiEnabled
    ? "Create a Civilization icon draft with OpenAI."
    : "This preset is NovelAI-only; OpenAI image creation stays limited to Civilization Icon.";
  novelPositive.disabled = promptEngine === "openai";
  novelNegative.disabled = promptEngine === "openai";
  if (promptEngine === "openai") {
    novelPositive.value = "";
    novelNegative.value = "";
    novelPositive.placeholder = "Civilization icons use the OpenAI prompt box on the right.";
    novelNegative.placeholder = "Not used for OpenAI civilization icons.";
    imagePromptStatus.textContent = "OpenAI prompt mode for Civilization icons.";
  } else {
    openaiImagePrompt.value = "";
    novelPositive.placeholder = "";
    novelNegative.placeholder = "";
    imagePromptStatus.textContent = "NovelAI prompt mode.";
  }
  document.querySelector("#openaiImageSize").value = preset.openai_size || "1024x1024";
  renderNovelSettings({
    resolution: preset.resolution,
    sampler: preset.sampler,
    steps: preset.steps,
    prompt_guidance: preset.prompt_guidance,
    seed: "random",
  });
}

async function generateNovelPrompt() {
  imagePromptStatus.textContent = "Asking OpenAI for prompt package...";
  const body = {
    asset_type: assetType.value,
    subject: imagePromptForm.elements.asset_subject.value,
    civilization: imagePromptForm.elements.asset_civilization.value,
    visual_brief: imagePromptForm.elements.asset_brief.value,
    style_tags: imagePromptForm.elements.style_tags.value,
    avoid: imagePromptForm.elements.avoid_tags.value,
    must_include: imagePromptForm.elements.must_include.value,
  };
  try {
    const payload = await fetchJson("/api/novelai-prompt", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    novelPositive.value = payload.positive_prompt || "";
    novelNegative.value = payload.undesired_content || "";
    const preset = state.assetPresets[assetType.value] || {};
    openaiImagePrompt.value = preset.openai_enabled !== false ? (payload.openai_prompt || "") : "";
    renderNovelSettings(payload.settings || {});
    imagePromptStatus.textContent = "Prompt package ready.";
  } catch (error) {
    imagePromptStatus.textContent = error.message;
  }
}

function renderNovelSettings(settings) {
  novelSettings.replaceChildren();
  for (const [key, value] of Object.entries(settings)) {
    const item = document.createElement("div");
    const label = document.createElement("span");
    label.textContent = key.replaceAll("_", " ");
    const strong = document.createElement("strong");
    strong.textContent = value;
    item.append(label, strong);
    novelSettings.append(item);
  }
}

async function createOpenAIAsset() {
  if (!openaiImagePrompt.value.trim()) {
    imagePromptStatus.textContent = "Generate or paste an OpenAI image prompt first.";
    return;
  }
  imagePromptStatus.textContent = "Creating OpenAI image...";
  openaiImageOutputs.replaceChildren();
  const body = {
    asset_type: assetType.value,
    prompt: openaiImagePrompt.value,
    model: document.querySelector("#openaiImageModel").value,
    size: document.querySelector("#openaiImageSize").value,
    quality: document.querySelector("#openaiImageQuality").value,
    background: document.querySelector("#openaiImageBackground").value,
    output_format: document.querySelector("#openaiImageFormat").value,
    output_dir: document.querySelector("#openaiImageOutput").value,
    filename: imagePromptForm.elements.asset_subject.value || assetType.value,
  };
  try {
    const payload = await fetchJson("/api/openai-image", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    renderOpenAIImages(payload);
    imagePromptStatus.textContent = "Image created.";
  } catch (error) {
    imagePromptStatus.textContent = error.message;
  }
}

function renderOpenAIImages(payload) {
  openaiImageOutputs.replaceChildren();
  for (const file of payload.generated_files || []) {
    const item = document.createElement("article");
    item.className = "fileItem";
    const img = document.createElement("img");
    img.src = file.url;
    img.alt = "";
    img.loading = "lazy";
    img.decoding = "async";
    const link = document.createElement("a");
    link.href = file.url;
    link.target = "_blank";
    link.textContent = file.path.split(/[\\/]/).pop();
    item.append(img, link);
    openaiImageOutputs.append(item);
  }
}

async function copyText(text) {
  if (!text) {
    return;
  }
  await navigator.clipboard.writeText(text);
  imagePromptStatus.textContent = "Copied.";
}

async function loadTemplates() {
  try {
    const payload = await fetchJson("/api/templates");
    state.templates = payload.templates || [];
    templateRoot.textContent = payload.template_root || "Template folder";
    templateForm.elements.template_output_dir.value = payload.default_output_dir || "output/template_copilot";
    renderTemplateFiles();
  } catch (error) {
    templateRoot.textContent = error.message;
  }
}

function clampCount(input, min, max) {
  const parsed = Number.parseInt(input.value, 10);
  const value = Math.min(max, Math.max(min, Number.isFinite(parsed) ? parsed : min));
  input.value = String(value);
  return value;
}

function snapshotEntityInputs() {
  const civs = Array.from(civEntityGrid.querySelectorAll("[data-civ-card]")).map((card) => ({
    name: card.querySelector("[data-civ-name]")?.value || "",
    demonym: card.querySelector("[data-civ-demonym]")?.value || "",
    cityNames: card.querySelector("[data-city-names]")?.value || "",
    citizenNames: card.querySelector("[data-citizen-names]")?.value || "",
    governorsEnabled: card.querySelector("[data-enable-governors]")?.checked || false,
    governorNames: card.querySelector("[data-governor-names]")?.value || "",
    governorDetails: card.querySelector("[data-governor-details]")?.value || "",
    namedGeography: card.querySelector("[data-named-geography]")?.value || "",
    uniquesEnabled: card.querySelector("[data-enable-uniques]")?.checked || false,
    unitNames: card.querySelector("[data-unit-names]")?.value || "",
    unitDetails: card.querySelector("[data-unit-details]")?.value || "",
    buildingNames: card.querySelector("[data-building-names]")?.value || "",
    buildingDetails: card.querySelector("[data-building-details]")?.value || "",
    improvementNames: card.querySelector("[data-improvement-names]")?.value || "",
    improvementDetails: card.querySelector("[data-improvement-details]")?.value || "",
    districtNames: card.querySelector("[data-district-names]")?.value || "",
    districtDetails: card.querySelector("[data-district-details]")?.value || "",
  }));
  const leaders = Array.from(leaderEntityGrid.querySelectorAll("[data-leader-card]")).map((card) => ({
    name: card.querySelector("[data-leader-name]")?.value || "",
    leaderId: card.querySelector("[data-leader-id]")?.value || "",
    civIndex: card.querySelector("[data-leader-civ]")?.value || "0",
  }));
  return {civs, leaders};
}

function renderEntityInputs() {
  if (!civCount || !leaderCount) {
    return;
  }
  const previous = snapshotEntityInputs();
  const civTotal = clampCount(civCount, 1, 4);
  const leaderTotal = clampCount(leaderCount, 1, 8);

  civEntityGrid.replaceChildren();
  for (let index = 0; index < civTotal; index += 1) {
    civEntityGrid.append(createCivilizationCard(index, previous.civs[index]));
  }

  leaderEntityGrid.replaceChildren();
  for (let index = 0; index < leaderTotal; index += 1) {
    leaderEntityGrid.append(createLeaderCard(index, previous.leaders[index], civTotal));
  }
  refreshLeaderCivilizationOptions();
  refreshCivilizationDerivedIds();
  refreshLeaderDerivedIds();
  updateAutoTemplateSelection();
}

function createCivilizationCard(index, values = {}) {
  const card = document.createElement("article");
  card.className = "entityCard";
  card.dataset.civCard = String(index);
  card.innerHTML = `
    <h4>Civilization ${index + 1} <span class="compulsoryTag">Core</span></h4>
    <label>
      Name <span class="compulsoryTag">Compulsory</span>
      <input data-civ-name name="civilization_name_${index}" value="${escapeAttr(values.name || defaultCivName(index))}" autocomplete="off">
    </label>
    <label>
      Demonym / adjective <span class="compulsoryTag">Compulsory</span>
      <input data-civ-demonym name="civilization_demonym_${index}" value="${escapeAttr(values.demonym || "")}" placeholder="Northbridger" autocomplete="off">
      <small class="fieldHelp">Separate from citizen names. Maps to the civilization adjective LOC.</small>
    </label>
    <label>
      City names <span class="compulsoryTag">Compulsory</span>
      <textarea data-city-names name="city_names_${index}" rows="3" placeholder="Northbridge&#10;Eastmere&#10;Rivergate">${escapeHtml(values.cityNames || "")}</textarea>
      <small class="fieldHelp">One city per line for this civilization only.</small>
    </label>
    <label>
      Citizen names <span class="compulsoryTag">Compulsory</span>
      <textarea data-citizen-names name="citizen_names_${index}" rows="2" placeholder="John&#10;Michael&#10;Emily">${escapeHtml(values.citizenNames || "")}</textarea>
      <small class="fieldHelp">Citizen personal names only, one per line. Not demonyms.</small>
    </label>
    <div class="linkedUniquesPanel corePanel">
      <label>
        Named geography <span class="compulsoryTag">Compulsory</span>
        <textarea data-named-geography name="named_geography_${index}" rows="5" placeholder="Rivers: North River, Silver Bend&#10;Lakes: Lake John, Lake Smith&#10;Seas: Inner Sea&#10;Deserts: Grey Desert&#10;Volcanoes: Mount Example&#10;Mountains: Northern Range">${escapeHtml(values.namedGeography || "")}</textarea>
        <small class="fieldHelp">Core Civilization.xml data. These map to NamedRiverCivilizations, NamedLakes, NamedLakeCivilizations, NamedSeas, NamedDeserts, NamedVolcanoes, and NamedMountainCivilizations, with LOC rows in Base text files.</small>
      </label>
    </div>
    <label class="check uniqueToggle">
      <input data-enable-governors type="checkbox" ${values.governorsEnabled ? "checked" : ""}>
      <span>
        <strong>Add unique governors</strong>
        <small class="fieldHelp">Optional. Turn this on only when this civilization needs custom governor XML, promotion text, and governor icons.</small>
      </span>
    </label>
    <div class="linkedUniquesPanel" data-governor-panel ${values.governorsEnabled ? "" : "hidden"}>
      <div class="linkedGrid detailed">
        <label>
          Governor names
          <textarea data-governor-names name="governor_names_${index}" rows="2" placeholder="Governor One&#10;Governor Two">${escapeHtml(values.governorNames || "")}</textarea>
          <small class="fieldHelp">Up to 8 per civilization. Each line becomes a GOVERNOR_, LOC, and icon target.</small>
        </label>
        <label>
          Governor details
          <textarea data-governor-details name="governor_details_${index}" rows="4" placeholder="Unique governor with title, short title, identity pressure, portrait names, trait, six promotions, prereq promotion tree, promotion modifiers, and LOC descriptions.">${escapeHtml(values.governorDetails || "")}</textarea>
          <small class="fieldHelp">Include title, short title, description, identity pressure, portrait IDs, trait, promotion names, promotion prereqs, modifiers, and what each promotion changes.</small>
        </label>
      </div>
    </div>
    <label class="check uniqueToggle">
      <input data-enable-uniques type="checkbox" ${values.uniquesEnabled ? "checked" : ""}>
      <span>
        <strong>Add linked units, buildings, improvements, and districts</strong>
        <small class="fieldHelp">Turn this on only when this civilization has unique content. Auto-template selection follows this switch.</small>
      </span>
    </label>
    <div class="linkedUniquesPanel" data-linked-uniques-panel ${values.uniquesEnabled ? "" : "hidden"}>
      <div class="linkedGrid detailed">
        <label>
          Unit names
          <textarea data-unit-names name="unit_names_${index}" rows="2" placeholder="Elite Guard">${escapeHtml(values.unitNames || "")}</textarea>
          <small class="fieldHelp">Max 5. Each line becomes a UNIT_, LOC, and icon target tied to this civ.</small>
        </label>
        <label>
          Unit mechanics
          <textarea data-unit-details name="unit_details_${index}" rows="4" placeholder="Replaces Swordsman. Melee, CLASS_MELEE, 3 moves, 40 combat, 2 maintenance, Iron Working prereq, strong vs cavalry, AI uses as attacker.">${escapeHtml(values.unitDetails || "")}</textarea>
          <small class="fieldHelp">Describe replacement, domain, formation, promotion class, cost, maintenance, moves, sight, combat/ranged/range/AA, prereq, tags, and AI role.</small>
        </label>
        <label>
          Building names
          <textarea data-building-names name="building_names_${index}" rows="2" placeholder="Assembly Hall">${escapeHtml(values.buildingNames || "")}</textarea>
          <small class="fieldHelp">Max 5. Use exact in-game display names, one per line.</small>
        </label>
        <label>
          Building mechanics
          <textarea data-building-details name="building_details_${index}" rows="4" placeholder="Unique Government Plaza building. Requires district, 180 cost, 1 maintenance, +2 culture, +1 Great Writer point, citizen slot, modifier for loyalty.">${escapeHtml(values.buildingDetails || "")}</textarea>
          <small class="fieldHelp">Include prereq district/tech/civic, cost, maintenance, purchase yield, advisor, citizen slots, yield changes, GP points, great works, and modifiers.</small>
        </label>
        <label>
          Improvement names
          <textarea data-improvement-names name="improvement_names_${index}" rows="2" placeholder="Memorial Park">${escapeHtml(values.improvementNames || "")}</textarea>
          <small class="fieldHelp">Max 5. Improvements usually need terrain/resource/build-unit rules.</small>
        </label>
        <label>
          Improvement mechanics
          <textarea data-improvement-details name="improvement_details_${index}" rows="4" placeholder="Builder improvement. Valid on flat Grassland/Plains, not adjacent to another copy. +1 culture, +1 appeal, tourism after Flight, plunder culture.">${escapeHtml(values.improvementDetails || "")}</textarea>
          <small class="fieldHelp">Mention valid terrains, features, resources, build unit, prereq, plunder, appeal, defense, yields, adjacency, tourism, modifiers, and requirements.</small>
        </label>
        <label>
          District names
          <textarea data-district-names name="district_names_${index}" rows="2" placeholder="Commons District">${escapeHtml(values.districtNames || "")}</textarea>
          <small class="fieldHelp">Max 5. Say what district it replaces when relevant.</small>
        </label>
        <label>
          District mechanics
          <textarea data-district-details name="district_details_${index}" rows="4" placeholder="Replaces Theater Square. Half cost, +2 culture adjacency from city center, 1 citizen slot, plunders culture, no population requirement, unlocks at Drama and Poetry.">${escapeHtml(values.districtDetails || "")}</textarea>
          <small class="fieldHelp">Include replacement, prereq, cost/progression, placement rules, population rules, citizen yields, adjacency, plunder, appeal/city strength, projects, and modifiers.</small>
        </label>
      </div>
    </div>
  `;
  return card;
}

function createLeaderCard(index, values = {}, civTotal = 1) {
  const card = document.createElement("article");
  card.className = "entityCard compact";
  card.dataset.leaderCard = String(index);
  card.innerHTML = `
    <h4>Leader ${index + 1}</h4>
    <label>
      Name
      <input data-leader-name name="leader_name_${index}" value="${escapeAttr(values.name || defaultLeaderName(index))}" autocomplete="off">
    </label>
    <label>
      In-game identifier
      <input data-leader-id name="leader_id_${index}" value="${escapeAttr(values.leaderId || "")}" placeholder="LEADER_JOHN_SMITH" autocomplete="off">
      <small class="fieldHelp">Used by XML, LOC, icons, fallback neutral portraits, and cropper JSON.</small>
    </label>
    <label>
      Civilization
      <select data-leader-civ name="leader_civ_${index}" data-selected="${escapeAttr(values.civIndex || String(Math.min(index, civTotal - 1)))}"></select>
      <small class="fieldHelp">This leader will generate IDs and text against the selected civilization.</small>
    </label>
  `;
  return card;
}

function toggleUniquePanel(card) {
  if (!card) {
    return;
  }
  toggleCardPanel(card, "[data-enable-uniques]", "[data-linked-uniques-panel]");
  toggleCardPanel(card, "[data-enable-governors]", "[data-governor-panel]");
}

function toggleCardPanel(card, toggleSelector, panelSelector) {
  const enabled = card.querySelector(toggleSelector)?.checked || false;
  const panel = card.querySelector(panelSelector);
  if (panel) {
    panel.hidden = !enabled;
  }
}

function defaultCivName(index) {
  return index === 0 ? "Neutral Commonwealth" : `Neutral Civilization ${index + 1}`;
}

function defaultLeaderName(index) {
  return index === 0 ? "John Smith" : `Leader ${index + 1}`;
}

function refreshLeaderCivilizationOptions() {
  const civNames = Array.from(civEntityGrid.querySelectorAll("[data-civ-name]"))
    .map((input, index) => input.value.trim() || `Civilization ${index + 1}`);
  leaderEntityGrid.querySelectorAll("[data-leader-civ]").forEach((select) => {
    const selected = select.value || select.dataset.selected || "0";
    select.replaceChildren();
    civNames.forEach((name, index) => {
      const option = document.createElement("option");
      option.value = String(index);
      option.textContent = name;
      select.append(option);
    });
    select.value = civNames[Number.parseInt(selected, 10)] ? selected : "0";
    select.dataset.selected = select.value;
  });
}

function refreshCivilizationDerivedIds() {
  civEntityGrid.querySelectorAll("[data-civ-card]").forEach((card) => {
    const demonym = card.querySelector("[data-civ-demonym]");
    if (demonym && !demonym.value.trim()) {
      const name = card.querySelector("[data-civ-name]")?.value.trim() || "";
      demonym.placeholder = name ? `${name} citizen adjective` : "Civilization adjective";
    }
  });
}

function refreshLeaderDerivedIds() {
  leaderEntityGrid.querySelectorAll("[data-leader-card]").forEach((card, index) => {
    const name = card.querySelector("[data-leader-name]")?.value.trim() || defaultLeaderName(index);
    const idInput = card.querySelector("[data-leader-id]");
    if (idInput && !idInput.value.trim()) {
      idInput.placeholder = `LEADER_${identifierFromName(name)}`;
    }
  });
}

function identifierFromName(value) {
  const cleaned = String(value || "")
    .trim()
    .replace(/[^A-Za-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toUpperCase();
  if (!cleaned) {
    return "GENERATED";
  }
  return /^\d/.test(cleaned) ? `X_${cleaned}` : cleaned;
}

function collectTemplateEntities() {
  const civilizations = Array.from(civEntityGrid.querySelectorAll("[data-civ-card]")).map((card, index) => {
    const uniquesEnabled = card.querySelector("[data-enable-uniques]")?.checked || false;
    const governorsEnabled = card.querySelector("[data-enable-governors]")?.checked || false;
    return {
      index,
      name: card.querySelector("[data-civ-name]")?.value.trim() || defaultCivName(index),
      demonym: card.querySelector("[data-civ-demonym]")?.value.trim() || "",
      city_names: splitLines(card.querySelector("[data-city-names]")?.value || ""),
      citizen_names: splitLines(card.querySelector("[data-citizen-names]")?.value || ""),
      governor_names: governorsEnabled ? splitLines(card.querySelector("[data-governor-names]")?.value || "").slice(0, 8) : [],
      governor_details: governorsEnabled ? card.querySelector("[data-governor-details]")?.value.trim() || "" : "",
      named_geography: card.querySelector("[data-named-geography]")?.value.trim() || "",
      unit_names: uniquesEnabled ? splitLines(card.querySelector("[data-unit-names]")?.value || "").slice(0, 5) : [],
      building_names: uniquesEnabled ? splitLines(card.querySelector("[data-building-names]")?.value || "").slice(0, 5) : [],
      improvement_names: uniquesEnabled ? splitLines(card.querySelector("[data-improvement-names]")?.value || "").slice(0, 5) : [],
      district_names: uniquesEnabled ? splitLines(card.querySelector("[data-district-names]")?.value || "").slice(0, 5) : [],
      unique_details: uniquesEnabled ? {
        units: card.querySelector("[data-unit-details]")?.value.trim() || "",
        buildings: card.querySelector("[data-building-details]")?.value.trim() || "",
        improvements: card.querySelector("[data-improvement-details]")?.value.trim() || "",
        districts: card.querySelector("[data-district-details]")?.value.trim() || "",
      } : {units: "", buildings: "", improvements: "", districts: ""},
    };
  });
  const leaders = Array.from(leaderEntityGrid.querySelectorAll("[data-leader-card]")).map((card, index) => {
    const civIndex = Number.parseInt(card.querySelector("[data-leader-civ]")?.value || "0", 10) || 0;
    const civilization = civilizations[civIndex] || civilizations[0];
    return {
      index,
      name: card.querySelector("[data-leader-name]")?.value.trim() || defaultLeaderName(index),
      leader_id: card.querySelector("[data-leader-id]")?.value.trim() || `LEADER_${identifierFromName(card.querySelector("[data-leader-name]")?.value.trim() || defaultLeaderName(index))}`,
      civilization_index: civilization?.index || 0,
      civilization: civilization?.name || defaultCivName(0),
    };
  });
  return {
    civilization_profiles: civilizations,
    leader_bindings: leaders,
    civilization_names: civilizations.map((item) => item.name).filter(Boolean),
    leader_names: leaders.map((item) => item.name).filter(Boolean),
    city_names: civilizations.flatMap((item) => item.city_names),
    citizen_names: civilizations.flatMap((item) => item.citizen_names),
    governor_names: civilizations.flatMap((item) => item.governor_names),
    governor_details: civilizations.map((item) => item.governor_details).filter(Boolean).join("\n\n"),
    unit_names: civilizations.flatMap((item) => item.unit_names),
    building_names: civilizations.flatMap((item) => item.building_names),
    improvement_names: civilizations.flatMap((item) => item.improvement_names),
    district_names: civilizations.flatMap((item) => item.district_names),
    named_geography: civilizations.map((item) => item.named_geography).filter(Boolean).join("\n\n"),
  };
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll('"', "&quot;");
}

async function extractXmlProfile() {
  const source = extractorSourcePath.value.trim();
  if (!source) {
    extractorStatus.textContent = "Enter a Civ VI XML file or mod folder path first.";
    return;
  }
  extractorStatus.textContent = "Extracting XML profile...";
  clearExtractorResults();
  try {
    const payload = await fetchJson("/api/xml-extractor/extract", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        path: source,
        out: extractorProfileOut.value.trim(),
      }),
    });
    extractorStatus.textContent = `Extracted ${payload.file_count || 0} XML file(s).`;
    renderExtractorResult(payload, "Extracted profile");
  } catch (error) {
    extractorStatus.textContent = error.message;
  }
}

async function summarizeXmlProfile() {
  const profile = extractorProfileOut.value.trim();
  if (!profile) {
    extractorStatus.textContent = "Enter the extracted profile path first.";
    return;
  }
  extractorStatus.textContent = "Summarizing profile...";
  clearExtractorResults();
  try {
    const payload = await fetchJson("/api/xml-extractor/summarize", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({profile}),
    });
    extractorStatus.textContent = "Summary ready.";
    renderExtractorResult(payload, "Profile summary");
  } catch (error) {
    extractorStatus.textContent = error.message;
  }
}

async function buildCopilotPrefillFromProfile() {
  const profile = extractorProfileOut.value.trim();
  if (!profile) {
    extractorStatus.textContent = "Enter the extracted profile path first.";
    return;
  }
  extractorStatus.textContent = "Building Copilot prefill...";
  clearExtractorResults();
  try {
    const payload = await fetchJson("/api/xml-extractor/copilot", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        profile,
        out: extractorPrefillOut.value.trim(),
      }),
    });
    extractorStatus.textContent = "Copilot prefill ready.";
    renderExtractorResult(payload, "Copilot prefill");
  } catch (error) {
    extractorStatus.textContent = error.message;
  }
}

function clearExtractorResults() {
  extractorLinks.replaceChildren();
  extractorSummary.replaceChildren();
  extractorJson.textContent = "{}";
}

function renderExtractorResult(payload, label) {
  if (payload.output_path) {
    const item = document.createElement("article");
    item.className = "templateOutput";
    const title = document.createElement("strong");
    title.textContent = label;
    const meta = document.createElement("span");
    meta.textContent = payload.output_path;
    const link = document.createElement("a");
    link.href = payload.output_url || "#";
    link.target = "_blank";
    link.textContent = "Open JSON";
    item.append(title, meta, link);
    extractorLinks.append(item);
  }
  const summary = payload.summary || {};
  renderExtractorSummary(summary);
  extractorJson.textContent = JSON.stringify(summary, null, 2);
}

function renderExtractorSummary(summary) {
  extractorSummary.replaceChildren();
  const cards = [
    ["Civilizations", summary.civilizations || []],
    ["Leaders", summary.leaders || []],
    ["Units", summary.units || []],
    ["Buildings", summary.buildings || []],
    ["Districts", summary.districts || []],
    ["Improvements", summary.improvements || []],
  ];
  for (const [title, values] of cards) {
    extractorSummary.append(summaryCard(title, values));
  }
  extractorSummary.append(summaryMetric("LOC keys", summary.localized_text_count || 0));
  extractorSummary.append(summaryMetric("Modifiers", summary.modifier_count || 0));
  extractorSummary.append(summaryMetric("Modifier args", summary.modifier_argument_count || 0));
  extractorSummary.append(summaryCard("Warnings", summary.warnings || []));
}

function summaryCard(title, values) {
  const card = document.createElement("article");
  card.className = "extractorCard";
  const heading = document.createElement("strong");
  heading.textContent = `${title}: ${values.length}`;
  const list = document.createElement("p");
  list.textContent = values.length ? values.slice(0, 12).join(", ") : "None detected";
  card.append(heading, list);
  return card;
}

function summaryMetric(title, value) {
  const card = document.createElement("article");
  card.className = "extractorCard metric";
  const heading = document.createElement("strong");
  heading.textContent = title;
  const number = document.createElement("span");
  number.textContent = String(value);
  card.append(heading, number);
  return card;
}

async function handleTemplateUpload() {
  const files = Array.from(templateUpload.files || []);
  const accepted = [];
  for (const file of files) {
    const suffix = file.name.split(".").pop()?.toLowerCase() || "";
    if (!["xml", "sql", "artdef", "txt"].includes(suffix)) {
      continue;
    }
    accepted.push({
      name: file.name,
      path: `uploaded/${file.name}`,
      kind: suffix === "txt" ? "xml" : suffix,
      content: await file.text(),
      uploaded: true,
    });
  }
  state.uploadedTemplates = accepted;
  renderTemplateFiles();
  templateStatus.textContent = accepted.length
    ? `Added ${accepted.length} uploaded template file(s) to the picker.`
    : "No supported uploaded template files found.";
}

async function handleCopilotPrefillLoad() {
  const file = copilotPrefillInput.files?.[0];
  if (!file) {
    return;
  }
  try {
    const prefill = JSON.parse(await file.text());
    applyCopilotPrefill(prefill);
    templateStatus.textContent = `Loaded ${file.name} into Template Copilot.`;
  } catch (error) {
    templateStatus.textContent = `Could not load copilot prefill: ${error.message}`;
  }
}

function applyCopilotPrefill(prefill) {
  const civilizations = normalizePrefillCivilizations(prefill);
  const leaders = normalizePrefillLeaders(prefill, civilizations);
  civCount.value = String(Math.min(4, Math.max(1, civilizations.length || 1)));
  leaderCount.value = String(Math.min(8, Math.max(1, leaders.length || 1)));
  renderEntityInputs();

  const civCards = Array.from(civEntityGrid.querySelectorAll("[data-civ-card]"));
  civilizations.slice(0, 4).forEach((civ, index) => {
    const card = civCards[index];
    if (!card) return;
    card.querySelector("[data-civ-name]").value = civ.name || defaultCivName(index);
    card.querySelector("[data-civ-demonym]").value = civ.demonym || "";
    card.querySelector("[data-city-names]").value = joinLines(civ.city_names);
    card.querySelector("[data-citizen-names]").value = joinLines(civ.citizen_names);
    const governorToggle = card.querySelector("[data-enable-governors]");
    governorToggle.checked = Boolean(civ.governors_enabled);
    card.querySelector("[data-governor-names]").value = joinLines(civ.governor_names);
    card.querySelector("[data-governor-details]").value = civ.governor_details || "";
    card.querySelector("[data-named-geography]").value = civ.named_geography || "";
    const uniqueToggle = card.querySelector("[data-enable-uniques]");
    uniqueToggle.checked = Boolean(civ.uniques_enabled);
    toggleUniquePanel(card);
    card.querySelector("[data-unit-names]").value = joinLines(civ.unit_names, 5);
    card.querySelector("[data-unit-details]").value = civ.unique_details?.units || "";
    card.querySelector("[data-building-names]").value = joinLines(civ.building_names, 5);
    card.querySelector("[data-building-details]").value = civ.unique_details?.buildings || "";
    card.querySelector("[data-improvement-names]").value = joinLines(civ.improvement_names, 5);
    card.querySelector("[data-improvement-details]").value = civ.unique_details?.improvements || "";
    card.querySelector("[data-district-names]").value = joinLines(civ.district_names, 5);
    card.querySelector("[data-district-details]").value = civ.unique_details?.districts || "";
  });

  refreshLeaderCivilizationOptions();
  const leaderCards = Array.from(leaderEntityGrid.querySelectorAll("[data-leader-card]"));
  leaders.slice(0, 8).forEach((leader, index) => {
    const card = leaderCards[index];
    if (!card) return;
    card.querySelector("[data-leader-name]").value = leader.name || defaultLeaderName(index);
    card.querySelector("[data-leader-id]").value = leader.leader_id || leader.id || `LEADER_${identifierFromName(leader.name || defaultLeaderName(index))}`;
    const civSelect = card.querySelector("[data-leader-civ]");
    const civIndex = civilizationIndexForLeader(leader, civilizations);
    civSelect.value = String(Math.max(0, civIndex));
    civSelect.dataset.selected = civSelect.value;
  });

  templateForm.elements.mod_code.value = prefill.mod_code || templateForm.elements.mod_code.value;
  appendPrefillContextToBrief(prefill);
  refreshCivilizationDerivedIds();
  refreshLeaderDerivedIds();
  updateAutoTemplateSelection();
}

function normalizePrefillCivilizations(prefill) {
  const profiles = Array.isArray(prefill.civilization_profiles) ? prefill.civilization_profiles : [];
  if (profiles.length) {
    return profiles.map((item, index) => ({
      index,
      name: item.name || item.id || defaultCivName(index),
      id: item.id || "",
      demonym: item.demonym || "",
      city_names: item.city_names || [],
      citizen_names: item.citizen_names || [],
      governor_names: item.governor_names || [],
      governor_details: item.governor_details || "",
      governors_enabled: Boolean((item.governor_names || []).length || item.governor_details),
      named_geography: item.named_geography || "",
      unit_names: item.unit_names || [],
      building_names: item.building_names || [],
      improvement_names: item.improvement_names || [],
      district_names: item.district_names || [],
      unique_details: normalizeUniqueDetails(item.unique_details),
      uniques_enabled: hasLinkedUniques(item),
    }));
  }
  return (prefill.civilization_names || [defaultCivName(0)]).slice(0, 4).map((name, index) => ({
    index,
    name,
    id: "",
    demonym: "",
    city_names: index === 0 ? (prefill.city_names || []) : [],
    citizen_names: index === 0 ? (prefill.citizen_names || []) : [],
    governor_names: index === 0 ? (prefill.governor_names || []) : [],
    governor_details: "",
    governors_enabled: index === 0 && Boolean((prefill.governor_names || []).length),
    named_geography: index === 0 ? (prefill.named_geography || "") : "",
    unit_names: index === 0 ? (prefill.unit_names || []) : [],
    building_names: index === 0 ? (prefill.building_names || []) : [],
    improvement_names: index === 0 ? (prefill.improvement_names || []) : [],
    district_names: index === 0 ? (prefill.district_names || []) : [],
    unique_details: {units: "", buildings: "", improvements: "", districts: ""},
    uniques_enabled: index === 0 && Boolean(
      (prefill.unit_names || []).length ||
      (prefill.building_names || []).length ||
      (prefill.improvement_names || []).length ||
      (prefill.district_names || []).length
    ),
  }));
}

function normalizeUniqueDetails(value = {}) {
  return {
    units: value.units || "",
    buildings: value.buildings || "",
    improvements: value.improvements || "",
    districts: value.districts || "",
  };
}

function hasLinkedUniques(item) {
  return Boolean(
    (item.unit_names || []).length ||
    (item.building_names || []).length ||
    (item.improvement_names || []).length ||
    (item.district_names || []).length ||
    Object.values(normalizeUniqueDetails(item.unique_details)).some(Boolean)
  );
}

function normalizePrefillLeaders(prefill, civilizations) {
  const bindings = Array.isArray(prefill.leader_bindings) ? prefill.leader_bindings : [];
  if (bindings.length) {
    return bindings;
  }
  return (prefill.leader_names || [defaultLeaderName(0)]).slice(0, 8).map((name, index) => ({
    index,
    name,
    leader_id: `LEADER_${identifierFromName(name)}`,
    civilization: civilizations[Math.min(index, civilizations.length - 1)]?.name || civilizations[0]?.name || "",
  }));
}

function civilizationIndexForLeader(leader, civilizations) {
  const byName = civilizations.findIndex((civ) => civ.name === leader.civilization);
  if (byName >= 0) return byName;
  const byId = civilizations.findIndex((civ) => civ.id && civ.id === leader.civilization_id);
  if (byId >= 0) return byId;
  return Number.isFinite(leader.civilization_index) ? leader.civilization_index : 0;
}

function joinLines(value, limit) {
  const items = Array.isArray(value) ? value : splitLines(String(value || ""));
  return (limit ? items.slice(0, limit) : items).join("\n");
}

function appendPrefillContextToBrief(prefill) {
  const locCount = (prefill.localization_keys || []).length;
  const iconCount = (prefill.detected_icons || []).length;
  const warnings = (prefill.warnings || []).slice(0, 5);
  const contextLines = [
    "",
    "Imported XML profile context:",
    `- LOC keys detected: ${locCount}`,
    `- Icons detected: ${iconCount}`,
  ];
  warnings.forEach((warning) => contextLines.push(`- Warning: ${warning}`));
  const brief = templateForm.elements.template_brief;
  if (!brief.value.includes("Imported XML profile context:")) {
    brief.value = `${brief.value.trim()}${contextLines.join("\n")}`.trim();
  }
}

function renderTemplateFilesLegacy() {
  templateFilesBox.replaceChildren();
  for (const template of state.templates) {
    const label = document.createElement("label");
    label.className = "templateFile";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = template.path;
    checkbox.dataset.kind = template.kind || "";
    checkbox.dataset.path = template.path;
    checkbox.checked = template.kind !== "artdef";

    const text = document.createElement("span");
    text.textContent = template.path;

    const meta = document.createElement("small");
    meta.textContent = `${(template.kind || "file").toUpperCase()} · ${template.placeholder_count} placeholders`;

    label.append(checkbox, text, meta);
    templateFilesBox.append(label);
  }
}

function setTemplateSelection(checked) {
  templateFilesBox.querySelectorAll("input[type='checkbox']").forEach((checkbox) => {
    checkbox.checked = checked;
  });
}

function selectTemplateGroupLegacy(group) {
  const matchers = {
    core: (path) => /(Civilization|Colors|Config|Religion)/i.test(path) && !/Icons|Texts|ArtDefs/i.test(path),
    leaders: (path) => /(Leader|Agenda)/i.test(path),
    units: (path) => /Unit/i.test(path),
    buildings: (path) => /Building|District|Project/i.test(path),
    icons: (path) => /(^|\/)Icons\//i.test(path),
    texts: (path) => /(^|\/)Texts\//i.test(path),
    artdefs: (path, kind) => kind === "artdef" || /(^|\/)ArtDefs\//i.test(path),
    sql: (path, kind) => kind === "sql" || /\.sql$/i.test(path),
  };
  const matcher = matchers[group];
  if (!matcher) {
    return;
  }
  templateFilesBox.querySelectorAll("input[type='checkbox']").forEach((checkbox) => {
    checkbox.checked = matcher(checkbox.dataset.path || checkbox.value, checkbox.dataset.kind || "");
  });
}

async function generateTemplatesLegacy() {
  const selected = Array.from(templateFilesBox.querySelectorAll("input[type='checkbox']:checked"))
    .map((checkbox) => checkbox.value);
  if (!selected.length) {
    templateStatus.textContent = "Select at least one XML, SQL, or ArtDef template.";
    return;
  }

  let manual = {};
  const manualText = templateForm.elements.manual_replacements.value.trim();
  if (manualText) {
    try {
      manual = JSON.parse(manualText);
    } catch (error) {
      templateStatus.textContent = `Manual JSON error: ${error.message}`;
      return;
    }
  }

  templateStatus.textContent = "Planning safe replacements and writing files...";
  templateOutputs.replaceChildren();
  replacementMap.textContent = "{}";

  const body = {
    files: selected,
    output_dir: templateForm.elements.template_output_dir.value,
    mod_code: templateForm.elements.mod_code.value,
    civilization_names: splitLines(templateForm.elements.civilization_names.value),
    leader_names: splitLines(templateForm.elements.leader_names.value),
    unit_names: splitLines(templateForm.elements.unit_names.value),
    building_names: splitLines(templateForm.elements.building_names.value),
    improvement_names: splitLines(templateForm.elements.improvement_names.value),
    governor_names: splitLines(templateForm.elements.governor_names.value),
    city_names: splitLines(templateForm.elements.city_names.value),
    citizen_names: splitLines(templateForm.elements.citizen_names.value),
    output_strategy: templateForm.elements.output_strategy.value,
    brief: templateForm.elements.template_brief.value,
    manual_replacements: manual,
  };

  try {
    const payload = await fetchJson("/api/template-copilot", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    renderTemplateOutputs(payload);
    templateStatus.textContent = `Generated ${payload.generated_files.length} file(s).`;
  } catch (error) {
    templateStatus.textContent = error.message;
  }
}

function renderTemplateFiles() {
  templateFilesBox.replaceChildren();
  for (const template of [...state.templates, ...state.uploadedTemplates]) {
    const label = document.createElement("label");
    label.className = "templateFile";
    if (template.uploaded) {
      label.classList.add("uploaded");
    }

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = template.path;
    checkbox.dataset.kind = template.kind || "";
    checkbox.dataset.path = template.path;
    checkbox.dataset.uploaded = template.uploaded ? "true" : "false";
    checkbox.checked = Boolean(template.uploaded);

    const text = document.createElement("span");
    text.textContent = template.path;

    const meta = document.createElement("small");
    const prefix = template.uploaded ? "UPLOADED " : "";
    meta.textContent = `${prefix}${(template.kind || "file").toUpperCase()} · ${template.placeholder_count ?? "new"} placeholders`;

    meta.textContent = `${prefix}${(template.kind || "file").toUpperCase()} - ${template.placeholder_count ?? "new"} placeholders`;
    label.append(checkbox, text, meta);
    templateFilesBox.append(label);
  }
  updateAutoTemplateSelection();
}

function selectTemplateGroup(group) {
  const matchers = {
    core: (path, kind) => (kind === "xml" || kind === "sql") && !/Icons|Texts|ArtDefs|uploaded\//i.test(path),
    districts: (path) => /District/i.test(path),
    governors: (path) => /Governor|Icons\/TemplateCiv_Icons/i.test(path),
    named: (path) => /^TemplateCiv_Civilization\.xml$/i.test(path) || /^Texts\/TemplateCiv_Base_/i.test(path),
    texts: (path) => /(^|\/)Texts\//i.test(path),
    sql: (path, kind) => kind === "sql" || /\.sql$/i.test(path),
  };
  const matcher = matchers[group];
  if (!matcher) {
    return;
  }
  let added = 0;
  templateFilesBox.querySelectorAll("input[type='checkbox']").forEach((checkbox) => {
    const matches = matcher(checkbox.dataset.path || checkbox.value, checkbox.dataset.kind || "");
    if (matches && !checkbox.checked) {
      added += 1;
    }
    checkbox.checked = checkbox.checked || matches;
  });
  templateStatus.textContent = added ? `Added ${added} ${group} template file(s).` : `All ${group} template files are already selected.`;
}

function updateAutoTemplateSelection() {
  if (!templateFilesBox) {
    return;
  }
  for (const checkbox of templateFilesBox.querySelectorAll("input[type='checkbox']")) {
    if (state.autoSelectedTemplatePaths.has(checkbox.value) && checkbox.dataset.uploaded !== "true") {
      checkbox.checked = false;
    }
  }
  const entities = collectTemplateEntities();
  const required = templateRequirementsForEntities(entities);
  state.autoSelectedTemplatePaths = required;
  for (const checkbox of templateFilesBox.querySelectorAll("input[type='checkbox']")) {
    if (required.has(checkbox.value)) {
      checkbox.checked = true;
    }
  }
}

function templateRequirementsForEntities(entities) {
  const required = new Set();
  const add = (...patterns) => {
    for (const template of state.templates) {
      const path = template.path || "";
      if (patterns.some((pattern) => pattern.test(path))) {
        required.add(path);
      }
    }
  };
  if (entities.civilization_names.length) {
    add(
      /^TemplateCiv_Civilization\.xml$/i,
      /^TemplateCiv_Config\.xml$/i,
      /^TemplateCiv_Colors\.xml$/i,
      /^Icons\/TemplateCiv_Icons\.xml$/i,
      /^Texts\/TemplateCiv_Base_/i,
      /^ArtDefs\/Civ6\.Art\.xml$/i,
      /^ArtDefs\/Civilizations\.artdef$/i,
      /^ArtDefs\/Cultures\.artdef$/i,
    );
  }
  if (entities.leader_names.length) {
    add(
      /^TemplateCiv_Leader\.xml$/i,
      /^TemplateCiv_Agenda\.xml$/i,
      /^Texts\/TemplateCiv_Leader_/i,
      /^Icons\/TemplateCiv_Icons\.xml$/i,
      /^ArtDefs\/FallbackLeaders\.artdef$/i,
    );
  }
  if (entities.unit_names.length) {
    add(
      /^TemplateCiv_Units\.xml$/i,
      /^TemplateCiv_Promotions\.xml$/i,
      /^TemplateCiv_PromotionModifiers\.xml$/i,
      /^Icons\/TemplateCiv_Icons\.xml$/i,
      /^ArtDefs\/Units\.artdef$/i,
    );
  }
  if (entities.building_names.length) {
    add(
      /^TemplateCiv_Buildings\.xml$/i,
      /^Icons\/TemplateCiv_Icons\.xml$/i,
      /^ArtDefs\/Buildings\.artdef$/i,
    );
  }
  if (entities.improvement_names.length) {
    add(
      /^TemplateCiv_Improvements\.xml$/i,
      /^ArtDefs\/Improvements\.artdef$/i,
    );
  }
  if (entities.district_names.length) {
    add(
      /^TemplateCiv_Districts\.xml$/i,
      /^TemplateCiv_DistrictModifiers\.xml$/i,
      /^TemplateCiv_Projects\.xml$/i,
      /^Icons\/TemplateCiv_Icons\.xml$/i,
      /^ArtDefs\/Districts\.artdef$/i,
    );
  }
  if (entities.governor_names.length || entities.governor_details) {
    add(
      /^TemplateCiv_Governor\.xml$/i,
      /^Texts\/TemplateCiv_Governor_/i,
      /^Icons\/TemplateCiv_Icons\.xml$/i,
    );
  }
  return required;
}

async function generateTemplates() {
  const checked = Array.from(templateFilesBox.querySelectorAll("input[type='checkbox']:checked"));
  const selected = checked
    .filter((checkbox) => checkbox.dataset.uploaded !== "true")
    .map((checkbox) => checkbox.value);
  const uploadedTemplates = checked
    .filter((checkbox) => checkbox.dataset.uploaded === "true")
    .map((checkbox) => state.uploadedTemplates.find((template) => template.path === checkbox.value))
    .filter(Boolean);
  if (!selected.length && !uploadedTemplates.length) {
    templateStatus.textContent = "Select at least one XML, SQL, or ArtDef template.";
    return;
  }

  let manual = {};
  const manualText = templateForm.elements.manual_replacements.value.trim();
  if (manualText) {
    try {
      manual = JSON.parse(manualText);
    } catch (error) {
      templateStatus.textContent = `Manual JSON error: ${error.message}`;
      return;
    }
  }

  templateStatus.textContent = "Planning safe replacements and writing files...";
  templateOutputs.replaceChildren();
  replacementMap.textContent = "{}";
  const entities = collectTemplateEntities();

  const body = {
    files: selected,
    uploaded_templates: uploadedTemplates.map(({name, kind, content}) => ({name, kind, content})),
    output_dir: templateForm.elements.template_output_dir.value,
    mod_code: templateForm.elements.mod_code.value,
    ...entities,
    use_api: templateForm.elements.use_api.checked,
    output_strategy: templateForm.elements.output_strategy.value,
    brief: templateForm.elements.template_brief.value,
    manual_replacements: manual,
  };

  try {
    const payload = await fetchJson("/api/template-copilot", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    renderTemplateOutputs(payload);
    templateStatus.textContent = `Generated ${payload.generated_files.length} file(s).`;
  } catch (error) {
    templateStatus.textContent = error.message;
  }
}

function renderTemplateOutputs(payload) {
  replacementMap.textContent = JSON.stringify(payload.replacements || {}, null, 2);
  templateOutputs.replaceChildren();
  for (const file of payload.generated_files || []) {
    const item = document.createElement("article");
    item.className = "templateOutput";

    const title = document.createElement("strong");
    title.textContent = file.path.split(/[\\/]/).pop();

    const meta = document.createElement("span");
    meta.textContent = `${file.replacement_count} replacements from ${file.template}${file.variant ? ` (${file.variant})` : ""}`;

    const link = document.createElement("a");
    link.href = file.url;
    link.target = "_blank";
    link.textContent = file.path;

    item.append(title, meta, link);
    templateOutputs.append(item);
  }
}

function splitLines(value) {
  return value
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function setAgentStatus(label, tone = "ready") {
  refs.statusPill.textContent = label;
  refs.statusPill.classList.toggle("busy", tone === "busy");
  refs.statusPill.classList.toggle("error", tone === "error");
}

function setEvent(message) {
  refs.eventLine.textContent = message;
}

function applyTheme(theme) {
  state.theme = theme;
  document.documentElement.dataset.theme = theme;
  refs.themeToggle.textContent = theme === "dark" ? "Light" : "Dark";
  localStorage.setItem("cropper-theme", theme);

  if (state.chatkit) {
    state.chatkit.setOptions(buildChatKitOptions());
  }
}

function applyPreset(name) {
  const presets = {
    leader: {
      mode: "leader_icons",
      subject_scale_percent: "108",
      vertical_offset_percent: "-2",
      horizontal_offset_percent: "0",
      unit_right_scale_percent: "108",
      remove_background: true,
      background_method: "advanced",
      clean_to_256: true,
    },
    unit: {
      mode: "unit_icons",
      base_name: "TemplateUnitAtlas",
      subject_scale_percent: "100",
      vertical_offset_percent: "0",
      horizontal_offset_percent: "0",
      unit_right_scale_percent: "100",
      remove_background: true,
      background_method: "advanced",
    },
    clean: {
      mode: "raw_256",
      subject_scale_percent: "108",
      vertical_offset_percent: "-2",
      horizontal_offset_percent: "0",
      unit_right_scale_percent: "108",
      remove_background: true,
      background_method: "advanced",
      clean_to_256: true,
    },
    diplo: {
      mode: "diplomacy_backgrounds",
      base_name: "DIPLOBG_CUSTOM",
      output_dir: "output/diplomacy_backgrounds",
      subject_scale_percent: "100",
      vertical_offset_percent: "0",
      horizontal_offset_percent: "0",
      unit_right_scale_percent: "100",
      remove_background: false,
      circle_enabled: false,
      clean_to_256: false,
      background_method: "advanced",
    },
    moment: {
      mode: "moment_pictures",
      base_name: "MOMENT_CUSTOM",
      output_dir: "output/moment_pictures",
      subject_scale_percent: "100",
      vertical_offset_percent: "0",
      horizontal_offset_percent: "0",
      unit_right_scale_percent: "100",
      remove_background: false,
      circle_enabled: false,
      clean_to_256: false,
      background_method: "advanced",
    },
    thumbnail: {
      mode: "thumbnails",
      base_name: "THUMBNAIL_CUSTOM",
      output_dir: "output/thumbnails",
      subject_scale_percent: "100",
      vertical_offset_percent: "0",
      horizontal_offset_percent: "0",
      unit_right_scale_percent: "100",
      remove_background: false,
      circle_enabled: false,
      clean_to_256: false,
      background_method: "advanced",
    },
  };
  const preset = presets[name];
  if (!preset) {
    return;
  }
  for (const [key, value] of Object.entries(preset)) {
    const field = form.elements[key];
    if (!field) {
      continue;
    }
    if (field.type === "checkbox") {
      field.checked = Boolean(value);
    } else {
      field.value = value;
    }
  }
  updateProfileInfo();
  switchPage("cropper");
}
