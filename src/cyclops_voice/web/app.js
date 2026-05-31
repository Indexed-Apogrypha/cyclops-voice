"use strict";
// Settings UI: loads /config, live-applies edits via debounced POST /config.
// Served from /ui/ on the daemon origin, so API calls are same-origin relative.

const $ = (id) => document.getElementById(id);
const FX = ["reverb_wet", "rasp_amount", "drive_db", "presence_gain_db"];
let cfg = null;            // canonical config mirror
let saveTimer = null;

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(path + " -> " + r.status);
  return r.status === 204 ? null : r.json();
}

function setStatus(ok) {
  const el = $("status");
  el.textContent = ok ? "daemon connected" : "daemon offline";
  el.className = "status " + (ok ? "ok" : "down");
}

// ---- tabs ----
document.querySelectorAll(".tab").forEach((t) => {
  t.onclick = () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    document.querySelector(`.panel[data-panel="${t.dataset.tab}"]`).classList.add("active");
  };
});

// ---- load ----
async function load() {
  cfg = await api("/config");
  // presets dropdown
  const presets = (await api("/presets")).presets || [cfg.voice.preset];
  fillSelect($("voice.preset"), presets, cfg.voice.preset);
  // devices dropdown
  try {
    const devs = (await api("/audio/devices")).devices || [];
    const opts = [{ value: "", text: "System default" }].concat(
      devs.map((d) => ({ value: d.name, text: d.name })));
    fillSelectOpts($("audio.output_device"), opts, cfg.audio.output_device || "");
  } catch (e) { /* devices optional */ }

  bindSimple();
  bindEffects();
  bindRadioMode();
  reflectModifierRow();
  setStatus(true);
}

function fillSelect(sel, items, value) {
  sel.innerHTML = "";
  items.forEach((it) => {
    const o = document.createElement("option");
    o.value = it; o.textContent = it; sel.appendChild(o);
  });
  sel.value = value;
}
function fillSelectOpts(sel, opts, value) {
  sel.innerHTML = "";
  opts.forEach((it) => {
    const o = document.createElement("option");
    o.value = it.value; o.textContent = it.text; sel.appendChild(o);
  });
  sel.value = value;
}

// Map of element id -> [section, key, type]
const SIMPLE = [
  ["voice.preset", "voice", "preset", "str"],
  ["voice.length_scale", "voice", "length_scale", "num"],
  ["voice.pitch_semitones", "voice", "pitch_semitones", "num"],
  ["read.trigger", "read", "trigger", "str"],
  ["read.modifier", "read", "modifier", "str"],
  ["read.auto_dismiss_menu", "read", "auto_dismiss_menu", "bool"],
  ["read.max_chars", "read", "max_chars", "int"],
  ["hotkeys.read_selection", "hotkeys", "read_selection", "str"],
  ["hotkeys.stop", "hotkeys", "stop", "str"],
  ["hotkeys.pause_resume", "hotkeys", "pause_resume", "str"],
  ["behavior.start_minimized", "behavior", "start_minimized", "bool"],
  ["behavior.read_dispatch", "behavior", "read_dispatch", "str"],
  ["audio.volume", "audio", "volume", "num"],
  ["audio.output_device", "audio", "output_device", "str"],
  ["service.host", "service", "host", "str"],
  ["service.port", "service", "port", "int"],
  ["service.auth_token", "service", "auth_token", "str"],
];

function getCtl(el, type) {
  if (type === "bool") return el.checked;
  if (type === "num") return parseFloat(el.value);
  if (type === "int") return parseInt(el.value, 10) || 0;
  return el.value;
}
function setCtl(el, type, v) {
  if (type === "bool") el.checked = !!v;
  else el.value = v;
}

function bindSimple() {
  SIMPLE.forEach(([id, sec, key, type]) => {
    const el = $(id);
    setCtl(el, type, cfg[sec][key]);
    updateOut(id);
    el.oninput = () => {
      cfg[sec][key] = getCtl(el, type);
      updateOut(id);
      if (id === "read.trigger") reflectModifierRow();
      scheduleSave();
    };
  });
  $("behavior.launch_on_login").checked = !!cfg.behavior.launch_on_login;
  $("behavior.launch_on_login").onchange = async (e) => {
    cfg.behavior.launch_on_login = e.target.checked;
    try {
      const res = await api("/autostart", postJson({ enabled: e.target.checked }));
      e.target.checked = res.enabled;
      cfg.behavior.launch_on_login = res.enabled;
    } catch (err) { /* ignore */ }
    scheduleSave();
  };
}

function updateOut(id) {
  const out = $(id + ".out");
  if (out) out.textContent = $(id).value;
}

function bindRadioMode() {
  document.querySelectorAll('input[name="read.mode"]').forEach((r) => {
    r.checked = r.value === cfg.read.mode;
    r.onchange = () => { cfg.read.mode = r.value; scheduleSave(); };
  });
}

function reflectModifierRow() {
  $("modifier-row").style.display = cfg.read.trigger === "modifier_rmb" ? "flex" : "none";
}

function bindEffects() {
  document.querySelectorAll(".effect").forEach((row) => {
    const fx = row.dataset.fx;
    const on = row.querySelector(".fx-on");
    const val = row.querySelector(".fx-val");
    const out = row.querySelector("output");
    val.min = row.dataset.min; val.max = row.dataset.max; val.step = row.dataset.step;
    const cur = cfg.voice.effects[fx];
    on.checked = cur !== null && cur !== undefined;
    val.value = on.checked ? cur : (parseFloat(row.dataset.max) / 2);
    out.textContent = val.value;
    row.classList.toggle("disabled", !on.checked);

    const apply = () => {
      row.classList.toggle("disabled", !on.checked);
      val.disabled = !on.checked;
      cfg.voice.effects[fx] = on.checked ? parseFloat(val.value) : null;
      out.textContent = val.value;
      scheduleSave();
    };
    on.onchange = apply;
    val.oninput = () => { out.textContent = val.value; if (on.checked) apply(); };
    val.disabled = !on.checked;
  });
}

// ---- save (debounced live-apply) ----
function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(save, 250);
}
async function save() {
  try {
    await api("/config", postJson(cfg));
    flashSaved();
    setStatus(true);
  } catch (e) { setStatus(false); }
}
function postJson(obj) {
  return { method: "POST", headers: { "Content-Type": "application/json" },
           body: JSON.stringify(obj) };
}
function flashSaved() {
  const s = $("saved"); s.textContent = "saved ✓"; s.classList.add("show");
  setTimeout(() => s.classList.remove("show"), 900);
}

// ---- preview / stop ----
$("preview").onclick = () =>
  api("/speak", postJson({ text: "Cyclops systems online. All readings nominal." }))
    .catch(() => setStatus(false));
$("stop").onclick = () => api("/stop", { method: "POST" }).catch(() => {});

// ---- health poll ----
async function poll() {
  try { await api("/health"); setStatus(true); }
  catch (e) { setStatus(false); }
}
setInterval(poll, 4000);

load().catch((e) => { console.error(e); setStatus(false); });
