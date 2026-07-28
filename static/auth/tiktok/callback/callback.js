const params = new URLSearchParams(window.location.search);
const code = params.get("code");
const state = params.get("state");
document.getElementById("code").textContent = code || "(vacío)";
document.getElementById("state").textContent = state || "(vacío)";
if (!code && !state) {
  document.getElementById("sin-parametros").hidden = false;
}
