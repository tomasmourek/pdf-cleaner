function upload() {
  const input = document.getElementById("fileInput");
  const status = document.getElementById("status");

  if (!input.files.length) {
    status.textContent = "Nejdřív vyber soubor.";
    return;
  }

  status.textContent = "Zatím demo UI: backend ještě neběží. Další krok bude lokální/serverové API.";
}
