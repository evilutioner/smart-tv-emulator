"use strict";
// Shared dashboard shell. Nothing here may name a platform; per-TV behaviour lives in
// /platforms/<id>.js and is loaded from the snapshot's platform id.
import { $, api, element } from "/dom.js";

let state, paused = false, filter = "all", lastEventId = 0, messageTimer, flashTimer;
let lastApplicationEventId = 0, applicationFlashTimer;
let platform = null, platformId = "", keyedFor = "";
const modules = new Map();
const indicators = new Map();
const DEFAULT_PRIMARY_KEYS = ["Home","Back","Info","Power","Up","Select","Down","Left","Right","VolumeUp","VolumeDown","VolumeMute","Rev","Play","Fwd","ChannelUp","ChannelDown"];
const LABELS = {Up:"↑",Down:"↓",Left:"←",Right:"→",Select:"OK",Info:"Info",Menu:"Menu",VolumeUp:"Vol +",VolumeDown:"Vol −",VolumeMute:"Mute",ChannelUp:"CH +",ChannelDown:"CH −",ChannelPrevious:"CH prev",Rev:"Rewind",Fwd:"Forward",Play:"Play",Pause:"Pause",InstantReplay:"Replay",Backspace:"Delete",PowerOff:"Sleep"};

function notify(text, error = false) { const box = $("message"); box.textContent = text; box.className = error ? "error" : ""; box.hidden = false; clearTimeout(messageTimer); if (!error) messageTimer = setTimeout(() => box.hidden = true, 5000); }
function action(button, path, body = () => ({}), success) {
  $(button).addEventListener("click", async () => { $(button).disabled = true; try { await api(path, "POST", body()); if (success) notify(success); } catch (error) { notify(error.message, true); } finally { $(button).disabled = false; } });
}
function bindSetting(id, key, type = "string") {
  $(id).addEventListener("change", async event => { const el = event.target;
    const value = type === "bool" ? el.checked : el.value;
    el.disabled = true;
    try { await api("settings", "PATCH", {[key]:value}); }
    catch (error) { notify(error.message, true); }
    finally { el.disabled = false; if (state) syncSetting(el, state.settings[key], true); }
  });
}
function syncSetting(el, value, force = false) { if (!force && (el === document.activeElement || el.disabled)) return; if (el.type === "checkbox") el.checked = value; else el.value = value; }
function syncOptions(id, items, selected, describe) {
  const select = $(id);
  const ids = items.map(item => `${item.id}:${item.availability || ""}`).join("\n");
  if (select.dataset.ids !== ids) {
    const fragment = document.createDocumentFragment();
    for (const item of items) {
      const option = element("option", "", describe(item));
      option.value = item.id;
      fragment.append(option);
    }
    select.replaceChildren(fragment);
    select.dataset.ids = ids;
  }
  syncSetting(select, selected);
}

// ── platform module ────────────────────────────────────────────────────────────────────────
// A module may export { primaryKeys, keyLabels, stylesheet, mount(root),
//                       mountSettings(root), update(state), unmount() }.
async function usePlatform(id) {
  if (platformId === id) return;
  if (platform && platform.unmount) platform.unmount();
  $("platform-panels").replaceChildren();
  $("platform-settings").replaceChildren();
  platform = null; platformId = id;
  if (!modules.has(id)) {
    let loaded = {};
    if (/^[a-z0-9-]+$/.test(id)) {
      try { loaded = (await import(`/platforms/${id}.js`)).default || {}; }
      catch (error) { notify(`No dashboard module for platform ${id}: ${error.message}`, true); }
    }
    modules.set(id, loaded);
  }
  if (platformId !== id) return;   // a later snapshot switched platform while this one loaded
  platform = modules.get(id);
  $("platform-style").href = platform.stylesheet || "";
  if (platform.mount) platform.mount($("platform-panels"));
  if (platform.mountSettings) platform.mountSettings($("platform-settings"));
}
function applyPlatform() {
  if (!state || !platform) return;
  if (keyedFor !== platformId) buildKeys(state.keys);
  if (platform.update) platform.update(state);
  paintKeys(state);
}
function buildKeys(keys) {
  indicators.clear();
  $("key-grid").replaceChildren();
  $("extra-keys").replaceChildren();
  const primary = platform.primaryKeys || DEFAULT_PRIMARY_KEYS;
  const labels = {...LABELS, ...(platform.keyLabels || {})};
  for (const key of [...primary.filter(key => keys.includes(key)), ...keys.filter(key => !primary.includes(key))]) {
    const el = element("div", "key-indicator"); el.dataset.key = key; el.title = key;
    el.append(element("span", "", labels[key] || key), element("small", "", "0"));
    $(primary.includes(key) ? "key-grid" : "extra-keys").append(el); indicators.set(key, el);
  }
  keyedFor = platformId;
}
function paintKeys(data) {
  for (const [key,el] of indicators) { el.querySelector("small").textContent = data.counts[key] || 0; el.classList.toggle("lit",data.held_keys.includes(key)); el.classList.remove("denied"); }
  if (data.last_key && data.last_key.id !== lastEventId) {
    lastEventId = data.last_key.id;
    const el = indicators.get(data.last_key.key);
    if (el && Date.now() - Date.parse(data.last_key.time) < 1500) {
      const cls = data.last_key.status === 200 ? "lit" : "denied"; el.classList.add(cls);
      clearTimeout(flashTimer); flashTimer = setTimeout(() => { if (!state.held_keys.includes(data.last_key.key)) el.classList.remove(cls); },900);
    }
  }
}

// One row per protocol the captured device exposes, switched independently of the others.
const KIND_TEXT = {https:"HTTPS", http:"HTTP", "tcp-raw":"TCP", "tcp-tls":"TLS", ssdp:"SSDP", mdns:"mDNS"};
function protocolWhere(item) {
  if (item.kind === "ssdp") return "239.255.255.250:1900";
  if (item.kind === "mdns") {
    const ports = item.advertised_ports?.length ? item.advertised_ports : [item.port];
    return `224.0.0.251:5353 · advertises ${ports.length === 1 ? "port" : "ports"} ${ports.join(", ")}`;
  }
  return `port ${item.port}`;
}
function protocolStatus(item) {
  if (item.error) return `error: ${item.error}`;
  if (item.listening) return "listening";
  if (item.armed) return "armed · opens on the first launch request";
  return item.enabled ? "starting…" : "off";
}
function syncProtocols(data) {
  const group = $("protocol-toggles");
  const items = data.protocols || [];
  const signature = items.map(item => item.id).join("\n");
  if (group.dataset.ids !== signature) {
    const fragment = document.createDocumentFragment();
    for (const item of items) {
      const row = element("div", "toggle-row");
      const copy = element("div");
      const label = element("label", "", item.primary ? `${item.label} · primary` : item.label);
      const input = element("input", "switch");
      input.type = "checkbox"; input.id = `protocol-${item.id}`; input.role = "switch";
      label.htmlFor = input.id;
      copy.append(label, element("p", "protocol-detail"));
      row.title = item.summary;
      row.append(copy, input);
      fragment.append(row);
      input.addEventListener("change", async () => {
        input.disabled = true;
        try { await api("settings", "PATCH", {protocols: {[item.id]: input.checked}}); }
        catch (error) { notify(error.message, true); }
        finally { input.disabled = false; }
      });
    }
    group.replaceChildren(fragment);
    group.dataset.ids = signature;
  }
  for (const item of items) {
    const input = $(`protocol-${item.id}`);
    syncSetting(input, item.enabled);
    const detail = input.parentElement.querySelector(".protocol-detail");
    detail.textContent = `${KIND_TEXT[item.kind] || item.kind} · ${protocolWhere(item)} · ${protocolStatus(item)}`;
    detail.className = `protocol-detail${item.error ? " warning-text" : ""}`;
  }
  const listening = items.filter(item => item.listening).length;
  $("protocol-note").textContent = !data.access.discoverable
    ? `Discovery paused by ${data.access.label}`
    : `${listening} of ${items.length} protocols listening`;
}

// ── keyboard tile ─────────────────────────────────────────────────────────────────────────
// A platform that declares no keyboard has no tile. Everything here is driven by the
// snapshot's keyboard block, so no platform is named.
let revealed = false;

function drawKeyboard(data) {
  const keyboard = data.keyboard;
  $("keyboard-card").hidden = !keyboard;
  if (!keyboard) return;
  const field = keyboard.field;
  $("keyboard-label").textContent = keyboard.label;
  $("keyboard-status").textContent = field.focused ? "Field focused" : "No field";
  $("keyboard-status").className = `badge ${field.focused ? "good" : "neutral"}`;
  $("keyboard-length").textContent = field.length;

  // The buffer is rendered read-only: every keystroke publishes a snapshot, so an input
  // bound to it would have its caret reset mid-type.
  const view = $("keyboard-text");
  const mask = field.hidden && !revealed;
  view.textContent = !field.focused && !field.text
    ? "No field focused"
    : (mask ? "\u2022".repeat(field.length) : field.text) || "(empty)";
  view.classList.toggle("empty", !field.text);
  $("keyboard-reveal").hidden = !field.hidden || !field.text;
  $("keyboard-reveal").textContent = revealed ? "Hide" : "Show";
  $("keyboard-source").textContent = field.source
    ? `Last written by ${field.source} over ${field.transport}.`
    : "Text typed here, or pushed in by a paired app, appears above.";

  syncSetting($("keyboard-focused"), field.focused);
  // A device that reports no field type has none to choose between.
  const types = keyboard.content_types;
  $("keyboard-type-setting").hidden = types.length < 2;
  if (types.length) {
    syncOptions("keyboard-content-type", types, field.content_type, item => item.label);
    const active = types.find(item => item.id === field.content_type);
    $("keyboard-type-hint").textContent = active && active.summary ? active.summary
      : "The field type the emulated device reports to a paired app.";
  }

  // Only the operations this platform's wire actually carries are offered.
  $("keyboard-send").hidden = $("keyboard-input").hidden = !keyboard.text_api;
  $("keyboard-backspace").hidden = !(keyboard.text_api || keyboard.delete_key);
  $("keyboard-enter").hidden = !(keyboard.text_api || keyboard.enter_key);
  $("keyboard-input").maxLength = keyboard.max_length;
  $("keyboard-note").textContent = keyboard.text_api
    ? `Writes travel as whole strings. Up to ${keyboard.max_length} characters.`
    : `This remote sends one ${keyboard.literal_prefix}<char> keypress per character, so ` +
      `text arrives from a remote app rather than from here.`;
}

// ── voice status tile ────────────────────────────────────────────────────────────────────
// Protocol adapters publish transitions and counters only. Raw audio never reaches the UI.
const VOICE_LABELS = {idle:"Idle", waiting:"Waiting", listening:"Listening",
  receiving:"Receiving", completed:"Completed", interrupted:"Interrupted"};

function byteSize(value) {
  if (value < 1024) return `${value} B`;
  return `${(value / 1024).toFixed(value < 10240 ? 1 : 0)} KiB`;
}
function duration(value) {
  if (value < 1000) return `${value} ms`;
  return `${(value / 1000).toFixed(1)} s`;
}
// What the emulator worked out about the audio stream, live. The bar is the signal level:
// -60 dBFS is empty and 0 is full, and it is only meaningful while audio is arriving.
function drawDetected(voice) {
  const found = voice.detected;
  const streaming = ["listening", "receiving"].includes(voice.state);
  $("voice-detected").textContent = found ? found.label : "—";
  const facts = found ? [`${found.confidence}`, found.basis] : [];
  if (found && streaming && found.bytes_per_second) facts.push(`${(found.bytes_per_second / 1000).toFixed(1)} kB/s`);
  if (found && found.level_db != null) facts.push(`level ${found.level_db} dBFS`);
  $("voice-detected-detail").textContent = found ? facts.join(" · ") : "Speak into the remote app to identify the stream.";
  const level = found && streaming && found.level_db != null ? Math.max(0, Math.min(1, (found.level_db + 60) / 60)) : 0;
  $("voice-level").style.width = `${Math.round(level * 100)}%`;
}
function drawVoice(data) {
  const voice = data.voice;
  $("voice-card").hidden = !voice;
  if (!voice) return;
  const active = ["waiting", "listening", "receiving"].includes(voice.state);
  $("voice-label").textContent = voice.label;
  $("voice-status").textContent = VOICE_LABELS[voice.state] || voice.state;
  $("voice-status").className = `badge ${active ? "good" : voice.state === "interrupted" ? "bad" : "neutral"}`;
  $("voice-session").textContent = voice.session_id || "—";
  $("voice-chunks").textContent = voice.chunks;
  $("voice-bytes").textContent = byteSize(voice.bytes);
  $("voice-duration").textContent = duration(voice.duration_ms);
  drawDetected(voice);
  $("voice-format").textContent = voice.format || "Control signal only · no audio transport";
  $("voice-detail").textContent = voice.detail || (voice.mode === "stream"
    ? "Waiting for an incoming audio stream. Audio is counted but never stored."
    : "Waiting for a voice start command. Audio travels outside this emulated API.");
}

// ── application launches ──────────────────────────────────────────────────────────────
// The shared UI knows only surface ids/labels supplied by the active platform. Native app
// ids and payloads stay opaque, so package names, DIAL names and Cast ids are never guessed.
const applicationCards = new Map();
function drawApplications(data) {
  const applications = data.applications;
  $("applications-card").hidden = !applications;
  if (!applications) return;
  $("applications-label").textContent = applications.label;
  const items = applications.items || [];
  const signature = items.map(item => `${item.key}\u0000${item.name}\u0000${item.available}`).join("\n");
  if ($("application-grid").dataset.signature !== signature) {
    applicationCards.clear();
    const fragment = document.createDocumentFragment();
    for (const item of items) {
      const card = element("div", `application-item${item.available ? "" : " unavailable"}`);
      card.dataset.key = item.key;
      card.append(element("strong", "", item.name), element("code", "", item.id),
                  element("small", "", `${item.surface_label}${item.catalogued ? " · catalogue" : " · observed"}`));
      fragment.append(card); applicationCards.set(item.key, card);
    }
    $("application-grid").replaceChildren(fragment);
    $("application-grid").dataset.signature = signature;
  }
  $("application-count").textContent = items.length;
  $("application-empty").hidden = items.length > 0;
  const launch = applications.last_launch;
  if (!launch) {
    $("applications-status").textContent = "Waiting";
    $("applications-status").className = "badge neutral";
    $("application-name").textContent = "—"; $("application-id").textContent = "—";
    $("application-surface").textContent = "—"; $("application-response").textContent = "—";
    $("application-payload").textContent = "No launch received";
    $("application-payload").classList.add("empty");
    $("application-detail").textContent = "Launch an app from the remote client to see the exact request here.";
    return;
  }
  const accepted = launch.status < 400;
  $("applications-status").textContent = accepted ? "Launch received" : "Launch rejected";
  $("applications-status").className = `badge ${accepted ? "good" : "bad"}`;
  $("application-name").textContent = launch.name;
  $("application-id").textContent = launch.id;
  $("application-surface").textContent = launch.surface_label;
  $("application-response").textContent = `Status ${launch.status}`;
  $("application-payload").textContent = launch.payload
    ? `${launch.payload}${launch.payload_truncated ? "\n… payload truncated" : ""}` : "(empty)";
  $("application-payload").classList.toggle("empty", !launch.payload);
  $("application-detail").textContent = `${new Date(launch.time).toLocaleTimeString("en-GB", {hour12:false})} · ${launch.transport.toUpperCase()}${launch.peer ? " / " + launch.peer : ""}${launch.detail ? " · " + launch.detail : ""}`;
  if (launch.event_id !== lastApplicationEventId) {
    lastApplicationEventId = launch.event_id;
    const card = applicationCards.get(launch.key);
    if (card) {
      clearTimeout(applicationFlashTimer);
      document.querySelectorAll(".application-item.launch-ok,.application-item.launch-failed")
        .forEach(item => item.classList.remove("launch-ok", "launch-failed"));
      card.classList.add(accepted ? "launch-ok" : "launch-failed");
      applicationFlashTimer = setTimeout(() => card.classList.remove("launch-ok", "launch-failed"), 1800);
    }
  }
}

function draw(data) {
  state = data;
  const settings = data.settings;
  document.title = `Smart TV Emulator · ${data.device.platform_name}`;
  $("platform-label").textContent = data.device.platform_name.toUpperCase();
  $("behaviour-title").textContent = `${data.device.platform_name} behaviour`;
  $("protocols-title").textContent = `${data.device.platform_name} protocols`;
  $("device-name").textContent = data.device.name;
  $("device-icon").textContent = data.device.platform_name.slice(0, 1).toUpperCase();
  $("device-protocol").textContent = `${data.device.platform_name} · IPv4 · ${data.device.protocol}`;
  // `software_version` is whatever version string a set reports; on several it is an API or
  // a service version, so it is not called the OS here. The picker label says which OS.
  $("device-profile-details").textContent = `${data.device.model_number} · software ${data.device.software_version} · S/N ${data.device.serial} · captured`;
  $("profile-hint").textContent = `Switches the ${data.device.platform_name} identity and captured wire responses. Existing device sessions are disconnected.`;
  // A platform this build does not include is still listed, marked with the word the API
  // supplies. Disabling the option would hide the explanation behind an unclickable row.
  syncOptions("platform", data.platforms, data.device.platform,
              item => item.availability === "n/a" ? `${item.display_name} \u00b7 N/A`
                                                  : item.display_name);
  drawLocked(data.platforms);
  syncOptions("device-profile", data.device_profiles, settings.device_profile,
              item => item.label);
  // A platform with a single access mode has no restriction setting to offer, so the group
  // states the one mode in force instead of presenting a selector that cannot change anything.
  const choose = data.access_modes.length > 1;
  $("access-setting").hidden = !choose;
  $("access-static").hidden = choose;
  if (choose) {
    syncOptions("access-mode", data.access_modes, settings.access_mode, item => item.label);
    $("access-hint").textContent = data.access.summary;
  } else $("access-static").textContent = `${data.access.label} · ${data.access.summary}`;
  syncProtocols(data);
  $("device-address").textContent = `${data.device.scheme}://${data.device.host}:${data.device.port}`;
  $("device-status").textContent = data.service_listening ? data.access.status_label : "No control protocol listening";
  $("device-status").className = `badge ${data.service_listening ? data.access.badge : "bad"}`;
  $("connections-count").textContent = data.connections.length;
  $("connection-count-label").textContent = "Active sessions";
  $("connections-list").textContent = data.connections.map(c => `${c.peer} · ${c.authenticated ? "authenticated" : "authenticating"} · ${c.id}`).join(" / ") || "No active sessions";
  $("connection-help").textContent = "Requests and client addresses appear in the event log.";
  $("accepted").textContent = data.accepted; $("rejected").textContent = data.rejected;
  $("last-key").textContent = data.last_key?.key || "—"; $("last-status").textContent = data.last_key?.status || "—";
  $("power-state").textContent = `Power: ${data.power ? "on" : "standby"}`;
  $("volume-state").textContent = `Volume: ${data.volume}${data.muted ? " · Mute" : ""}`;
  $("simulated-platform").textContent = `State is simulated; the ${data.device.platform_name} screen is not emulated`;
  $("limitations").textContent = data.limitations;
  $("empty-device").textContent = `Connect your remote app to the selected ${data.device.platform_name}.`;
  $("footer-platform").textContent = `${data.device.platform_name} adapter · v0.1`;
  if (data.device.platform !== platformId) usePlatform(data.device.platform).then(applyPlatform);
  else applyPlatform();
  drawKeyboard(data);
  drawVoice(data);
  drawApplications(data);
  if (!paused) drawLog();
}
function drawLog() {
  if (!state) return;
  const entries = state.events.filter(e => filter === "all" || filter === "errors" && e.status >= 400 || e.kind === filter).slice().reverse();
  $("event-count").textContent = `${entries.length}`; $("log-empty").hidden = entries.length > 0;
  const fragment = document.createDocumentFragment();
  for (const e of entries) {
    const row = element("tr"); const values = [new Date(e.time).toLocaleTimeString("en-GB",{hour12:false}), `${e.transport.toUpperCase()}${e.peer ? " / " + e.peer : ""}`,e.operation,e.status == null ? "—" : String(e.status),e.detail || (e.request_id ? `request-id: ${e.request_id}` : "—")];
    for (let i=0;i<values.length;i++) { const cell = element("td"); if (i===3 && e.status != null) { cell.append(element("span", `status-code ${e.status >= 400 ? "error" : ""}`, values[i])); } else cell.textContent = values[i]; row.append(cell); }
    fragment.append(row);
  }
  $("log-body").replaceChildren(fragment);
}
function connect() {
  const ws = new WebSocket(`ws://${location.host}/api/v1/events`);
  ws.onopen = () => { $("panel-status").textContent = "Dashboard connected"; $("panel-status").className = "badge good"; };
  ws.onmessage = event => { try { draw(JSON.parse(event.data)); } catch (error) { notify(`Invalid dashboard data: ${error.message}`,true); } };
  ws.onclose = () => { $("panel-status").textContent = "Dashboard disconnected"; $("panel-status").className = "badge bad"; setTimeout(connect,1500); };
  ws.onerror = () => ws.close();
}
// ── platforms this build does not include ──────────────────────────────────────────────────
// They are ordinary rows in the snapshot carrying their own name, summary and link, so the
// shell explains them without knowing which televisions exist.
function drawLocked(platforms) {
  const pending = platforms.filter(item => item.availability === "n/a");
  const note = $("platform-locked");
  note.hidden = !pending.length;
  if (!pending.length) return;
  const key = pending.map(item => item.id).join("\n");
  if (note.dataset.ids === key) return;
  note.dataset.ids = key;
  const link = element("a", "", "Ask about them");
  link.href = pending[0].contact || "";
  link.target = "_blank"; link.rel = "noopener";
  note.replaceChildren(
    document.createTextNode(
      `${pending.length} more ${pending.length === 1 ? "television is" : "televisions are"} ` +
      `emulated but not available in this build (N/A): ` +
      `${pending.map(item => item.display_name).join(", ")}. `),
    link);
}

function showUpsell(info) {
  $("upsell-title").textContent = info.error || "";
  $("upsell-summary").textContent = info.summary || "";
  $("upsell-devices").textContent = info.devices ? `Captured devices: ${info.devices}` : "";
  $("upsell-devices").hidden = !info.devices;
  const link = $("upsell-link");
  link.hidden = !info.contact;
  if (info.contact) link.href = info.contact;
  $("platform-upsell").hidden = false;
}

// Platform is runtime state, not a setting, so it has its own endpoint rather than a settings patch.
$("platform").addEventListener("change", async event => {
  const el = event.target; el.disabled = true;
  $("platform-upsell").hidden = true;
  try { await api("platform", "POST", {platform: el.value}); }
  catch (error) {
    // A platform this build does not include is an answer, not a fault: explain it.
    if (error.body && error.body.reason === "n/a") showUpsell(error.body);
    else notify(error.message, true);
  }
  finally { el.disabled = false; if (state) syncSetting(el, state.device.platform, true); }
});
bindSetting("device-profile","device_profile"); bindSetting("access-mode","access_mode");
action("disconnect","actions/disconnect"); action("reset-state","actions/reset"); action("clear-log","actions/clear-log");
action("save-settings","settings/save",() => ({}),"Settings saved. They will be loaded at the next startup.");
async function textAction(body) {
  try { await api("actions/text", "POST", body); }
  catch (error) { notify(error.message, true); }
}
$("keyboard-focused").addEventListener("change", async event => {
  const el = event.target; el.disabled = true;
  try { await api("actions/field", "POST", {focused: el.checked}); }
  catch (error) { notify(error.message, true); }
  finally { el.disabled = false; if (state && state.keyboard) syncSetting(el, state.keyboard.field.focused, true); }
});
$("keyboard-content-type").addEventListener("change", async event => {
  const el = event.target; el.disabled = true;
  // Choosing a type is how an app on the TV opens that kind of field.
  try { await api("actions/field", "POST", {focused: true, content_type: el.value}); }
  catch (error) { notify(error.message, true); }
  finally { el.disabled = false; }
});
async function sendText() {
  const input = $("keyboard-input");
  if (!input.value) return;
  const text = input.value;
  try { await api("actions/text", "POST", {op: "insert", text}); input.value = ""; }
  catch (error) { notify(error.message, true); }
}
$("keyboard-send").onclick = sendText;
$("keyboard-input").addEventListener("keydown", event => { if (event.key === "Enter") sendText(); });
$("keyboard-backspace").onclick = () => textAction({op: "delete", count: 1});
$("keyboard-enter").onclick = () => textAction({op: "enter"});
$("keyboard-clear").onclick = () => textAction({op: "clear"});
$("keyboard-reveal").onclick = () => { revealed = !revealed; if (state) drawKeyboard(state); };
$("pause-log").onclick = () => { paused=!paused; $("pause-log").textContent = paused ? "Resume" : "Pause"; if (!paused) drawLog(); };
document.querySelectorAll("[data-filter]").forEach(button => button.onclick = () => { filter=button.dataset.filter; document.querySelectorAll("[data-filter]").forEach(el=>el.classList.toggle("active",el===button)); if (!paused) drawLog(); });
connect();
