const state = {
  left: null,
  right: null,
};

const elements = {
  compareButton: document.querySelector("#compareButton"),
  resultPanel: document.querySelector("#resultPanel"),
  errorBox: document.querySelector("#errorBox"),
  decision: document.querySelector("#decision"),
  score: document.querySelector("#score"),
  phashMetric: document.querySelector("#phashMetric"),
  ssimMetric: document.querySelector("#ssimMetric"),
  dhashMetric: document.querySelector("#dhashMetric"),
  histMetric: document.querySelector("#histMetric"),
  diffImage: document.querySelector("#diffImage"),
};

wireDropZone("left");
wireDropZone("right");
elements.compareButton.addEventListener("click", compare);

function wireDropZone(side) {
  const drop = document.querySelector(`#${side}Drop`);
  const input = document.querySelector(`#${side}Input`);

  drop.addEventListener("click", () => input.click());
  input.addEventListener("change", () => setFile(side, input.files[0]));

  ["dragenter", "dragover"].forEach((eventName) => {
    drop.addEventListener(eventName, (event) => {
      event.preventDefault();
      drop.classList.add("dragging");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    drop.addEventListener(eventName, (event) => {
      event.preventDefault();
      drop.classList.remove("dragging");
    });
  });

  drop.addEventListener("drop", (event) => {
    const file = event.dataTransfer.files[0];
    setFile(side, file);
  });
}

function setFile(side, file) {
  if (!file || !file.type.startsWith("image/")) {
    showError("Choisis un fichier image valide.");
    return;
  }

  state[side] = file;
  const preview = document.querySelector(`#${side}Preview`);
  const meta = document.querySelector(`#${side}Meta`);
  preview.src = URL.createObjectURL(file);
  meta.textContent = `${file.name} · ${formatBytes(file.size)}`;
  elements.compareButton.disabled = !(state.left && state.right);
  hideError();
}

async function compare() {
  const form = new FormData();
  form.append("left", state.left);
  form.append("right", state.right);

  elements.compareButton.disabled = true;
  elements.compareButton.textContent = "Comparaison...";
  hideError();

  try {
    const response = await fetch("/api/compare", { method: "POST", body: form });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "La comparaison a échoué.");
    }
    renderResult(payload);
  } catch (error) {
    showError(error.message);
  } finally {
    elements.compareButton.disabled = false;
    elements.compareButton.textContent = "Comparer";
  }
}

function renderResult(result) {
  elements.resultPanel.hidden = false;
  elements.decision.textContent = labelDecision(result.decision);
  elements.score.textContent = `${result.score_percent} % de similarité globale`;
  elements.phashMetric.textContent = `${result.metrics.phash_similarity_percent} %`;
  elements.ssimMetric.textContent = `${result.metrics.ssim_percent} %`;
  elements.dhashMetric.textContent = `${result.metrics.dhash_similarity_percent} %`;
  elements.histMetric.textContent = `${result.metrics.histogram_percent} %`;
  elements.diffImage.src = result.diff_image;
}

function labelDecision(decision) {
  if (decision === "identiques") return "Identiques";
  if (decision === "similaires") return "Similaires";
  return "Différentes";
}

function showError(message) {
  elements.errorBox.hidden = false;
  elements.errorBox.textContent = message;
}

function hideError() {
  elements.errorBox.hidden = true;
  elements.errorBox.textContent = "";
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}
