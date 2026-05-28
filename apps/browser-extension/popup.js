const enabled = document.getElementById("enabled");
const token = document.getElementById("token");
const save = document.getElementById("save");

chrome.storage.local.get({ enabled: false, token: "" }, (settings) => {
  enabled.checked = Boolean(settings.enabled);
  token.value = settings.token || "";
});

save.addEventListener("click", () => {
  chrome.storage.local.set({ enabled: enabled.checked, token: token.value.trim() }, () => {
    save.textContent = "Saved";
    setTimeout(() => {
      save.textContent = "Save";
    }, 1200);
  });
});
