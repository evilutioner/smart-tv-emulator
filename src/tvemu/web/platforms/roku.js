"use strict";
let listening;
// Roku dashboard contributions. ECP is stateless over HTTP and has no pairing UI.
export default {
  // InstantReplay is on the physical Roku remote; Menu and Pause are not.
  primaryKeys: ["Home","Back","Info","Power","Up","Select","Down","Left","Right","VolumeUp","VolumeDown","VolumeMute","Rev","Play","Fwd","InstantReplay","ChannelUp","ChannelDown"],
  keyLabels: { Info: "Star ✳" },
  stylesheet: "/platforms/roku.css",
  mount(root) {
    listening = document.createElement("p");
    listening.className = "hint roku-listening";
    root.append(listening);
  },
  update(state) {
    if (!listening) return;
    const sessions = state.connections.filter(c => c.audio).map(c => c.audio);
    listening.textContent = sessions.length ? sessions.map(a =>
      `Private listening: ${a.transport} · ${a.state} · ${a.packets} packets · ${a.feedback} feedback · ${a.bytes} bytes${a.experimental ? " · experimental" : ""}`
    ).join(" / ") : "Private listening: idle. Test audio is available on profiles with an audio listener.";
    const last = state.events.filter(e => e.operation === "private-listening.error" ||
      e.operation === "private-listening.start").at(-1);
    if (last?.operation === "private-listening.error") listening.textContent += ` Error: ${last.detail}`;
  },
  unmount() { listening?.remove(); listening = null; },
};
