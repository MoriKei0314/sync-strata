// Settings of one installation (11/14). Nothing secret goes here: this file is served to anyone who can open the page.
// The host (or the person installing) may replace this file; every value has a working default.
// Things that used to be written into the scripts for one machine (the public name, a Windows path, the model's
// display name, the RAM Strata takes) live here instead.
"use strict";

const DSH_CONFIG = Object.freeze({
  // The model family shown before "Sync-M R7" etc. in the model picker and the box ("" = only the pack and rank).
  modelFamily: "Qwen3.8 Flash-Next",
  // Strata's start settings the relay knows (POST /m/strata/start?preset=<key>): key -> shown name. The first is the usual one.
  strataPresets: { syncm: "Sync-M", syncs: "Sync-S" },
  // The model a new session starts with when it is in dsh's list (otherwise dsh's own default).
  newSessionModel: { provider: "strata", model: "strata-r4", reasoningEffort: "low" },
  // Only these model providers are offered (dsh may also list paid APIs that this setup must never use).
  allowedProviders: ["strata"],
  // About how much RAM Strata takes when it runs, for the notes on the Strata sheet (GiB; 0 = do not say).
  strataRamGiB: 23,
  // The example in the "add a folder" box (a path on the PC that runs dsh).
  workspacePathExample: "/home/user/projects/app",
  // Where the PC's own dsh page listens, as shown in the login help.
  dshLocalUrl: "http://127.0.0.1:3080",
});
