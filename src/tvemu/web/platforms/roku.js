"use strict";
// Roku dashboard contributions. ECP is stateless over HTTP and has no pairing UI.
export default {
  // InstantReplay is on the physical Roku remote; Menu and Pause are not.
  primaryKeys: ["Home","Back","Info","Power","Up","Select","Down","Left","Right","VolumeUp","VolumeDown","VolumeMute","Rev","Play","Fwd","InstantReplay","ChannelUp","ChannelDown"],
  keyLabels: { Info: "Star ✳" },
};
