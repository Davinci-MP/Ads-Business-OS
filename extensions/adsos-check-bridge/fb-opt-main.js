// fb-opt-main.js - MAIN world hooks via co flags and cross-world messaging
// IMPORTANT: This file runs in the MAIN world (document has full DOM access)
// Cross-world communication with ISOLATED world (fb-opt-relay.js) uses window.postMessage

(function() {
  const co = {
    prevent_facebook_feed_reload: false,
    block_seen_story_facebook: false,
    block_seen_chat: false,
    block_typing_chat: false,
  };

  // ================================================================
  // Cross-world messaging with ISOLATED world (fb-opt-relay.js)
  // ================================================================
  window.addEventListener("message", (e) => {
    // Only accept messages from same window (no iframe sandbox bypass)
    if (e.source !== window) return;

    // EXTFBOPT_READY from ISOLATED world
    if (e.data?.type === "EXTFBOPT_READY") {
      // Initialize co flags from storage
      chrome.storage.local.get(["extFbOptimize"], (res) => {
        if (res.extFbOptimize) {
          Object.assign(co, res.extFbOptimize);
        }
      });
      // Signal readiness back
      window.postMessage({ type: "EXTFBOPT_ACK" }, "*");
      return;
    }

    // EXTFBOPT_CFG from ISOLATED world
    if (e.data?.type === "EXTFBOPT_CFG") {
      const cfg = e.data.cfg || {};
      Object.assign(co, cfg);
      // Persist to storage for ISOLATED world
      chrome.storage.local.set({ extFbOptimize: cfg });
      window.postMessage({ type: "EXTFBOPT_CFG_ACK" }, "*");
      return;
    }

    // EXTFBOPT_CFG_UPDATED fallback
    if (e.data?.type === "EXTFBOPT_CFG_UPDATED") {
      const cfg = e.data.cfg || {};
      Object.assign(co, cfg);
      chrome.storage.local.set({ extFbOptimize: cfg });
      return;
    }
  });

  // ================================================================
  // Facebook Feed Reload Prevention
  // ================================================================
  // Override document.hidden / visibilityState when enabled
  if (co.prevent_facebook_feed_reload) {
    try {
      const realHidden = Object.getOwnPropertyDescriptor(document, "hidden");
      Object.defineProperty(document, "hidden", {
        get() { return false; },
        configurable: true,
      });
      Object.defineProperty(document, "visibilityState", {
        get() { return "visible"; },
        configurable: true,
      });
    } catch (_) {}
  }

  // ================================================================
  // Block storiesUpdateSeenStateMutation across all transports
  // ================================================================
  if (co.block_seen_story_facebook || co.block_seen_chat || co.block_typing_chat) {
    try {
      // Block via window.fetch
      const origFetch = window.fetch;
      window.fetch = function(input, init) {
        try {
          if (typeof input === "string" && input.includes("storiesUpdateSeenStateMutation")) {
            init = init || {};
            init.method = "POST";
            init.body = JSON.stringify({ status: "blocked" });
          }
          return origFetch.call(this, input, init);
        } catch (_) { return null; }
      };

      // Block via XMLHttpRequest
      const origXHR = window.XMLHttpRequest.prototype.send;
      window.XMLHttpRequest.prototype.send = function(body) {
        try {
          if (body && typeof body === "string" && body.includes("storiesUpdateSeenStateMutation")) {
            this.body = JSON.stringify({ status: "blocked" });
          }
        } catch (_) {}
        try { origXHR.call(this, body); } catch (_) {}
      };

      // Block via navigator.sendBeacon
      const origBeacon = navigator.sendBeacon;
      navigator.sendBeacon = function(url, data) {
        try {
          if (typeof data === "string" && data.includes("storiesUpdateSeenStateMutation")) {
            return false;
          }
        } catch (_) {}
        try { return origBeacon.call(this, url, data); } catch (_) { return false; }
      };
    } catch (_) {}
  }

  // ================================================================
  // MQTT /ls_req Frame Rewriting for block_seen_chat & block_typing_chat
  // ================================================================
  if (co.block_seen_chat || co.block_typing_chat) {
    try {
      const origWS = WebSocket.prototype.send;
      WebSocket.prototype.send = function(frame) {
        try {
          if (frame && typeof frame === "string") {
            // Check if this is an /ls_req message
            const isLsReq = frame.includes("/ls_req");

            if (isLsReq) {
              try {
                // Parse minimal MQTT frame: docVarint, then JSON payload
                function readVarint(buf, offset) {
                  let result = 0;
                  let shift = 0;
                  while (offset < buf.length) {
                    const byte = buf[offset];
                    result |= (byte & 0x7F) << shift;
                    offset++;
                    if ((byte & 0x80) === 0) break;
                    shift += 7;
                  }
                  return { value: result, nextOffset: offset };
                }

                const buf = new TextEncoder().encode(frame);
                const varintResult = readVarint(buf, 0);

                // After varint comes the JSON payload
                const payloadStart = varintResult.nextOffset;
                const payloadStr = new TextDecoder().decode(buf.slice(payloadStart));
                const goc = JSON.parse(payloadStr);

                // Block typing packets (type 4) when co.block_typing_chat
                if (co.block_typing_chat && goc.type === 4 && goc.thread_key) {
                  try { return; } catch (_) {} // drop the packet silently
                }

                // Block seen chat (type 3) - rewrite watermark for type 21
                if (co.block_seen_chat && goc.type === 3) {
                  try {
                    if (goc.than && goc.than.tasks) {
                      goc.than.tasks = goc.than.tasks.map(t => {
                        try {
                          if (typeof t === "object" && t.label && String(t.label) === "21") {
                            const uid = "";
                            t.payload = JSON.stringify({
                              thread_id: uid,
                              last_read_watermark_ts: Date.now() * 1000
                            });
                          }
                          return t;
                        } catch (_) { return t; }
                      });
                    }
                    const rewrittenPayload = JSON.stringify(goc);
                    const rewrittenBuf = new TextEncoder().encode(rewrittenPayload);
                    const newFrame = rewrittenBuf.toString();
                    try { origWS.call(this, newFrame); } catch (_) {}
                    return;
                  } catch (_) {}
                }
              } catch (_) {}
              // If not a block scenario, just rewrite label "21" to current UID
              const uid = co.block_seen_chat ? "" : "";
              try {
                const rewritten = frame.replace(/"label"\s*:\s*"21"/, `"label": "${uid}"`);
                origWS.call(this, rewritten);
              } catch (_) {}
            } else {
              try {
                origWS.call(this, frame);
              } catch (_) {}
            }
          } else {
            try { origWS.call(this, frame); } catch (_) {}
          }
        } catch (_) {}
      };
    } catch (_) {}
  }

  // ================================================================
  // MQTT Frame Helpers (docVarint, ghiVarint, bocPublish, dungPublish)
  // These are utility functions, not executed on load
  // ================================================================
  try {
    function docVarint(buf, offset = 0) {
      let result = 0;
      let bit = 0;
      let byte;
      do {
        byte = buf[offset];
        result |= (byte & 0x7F) << bit;
        bit += 7;
        offset++;
      } while (byte & 0x80);
      return { value: result, nextOffset: offset };
    }

    function ghiVarint(buf, value, offset = 0) {
      let byte;
      do {
        byte = value & 0x7F;
        value >>= 7;
        buf[offset] = byte | (value > 0 ? 0x80 : 0);
        offset++;
      } while (value > 0);
      return offset;
    }

    function bocPublish(topic, payloadObj) {
      const topicBuf = new TextEncoder().encode(topic);
      const payloadBuf = new TextEncoder().encode(JSON.stringify(payloadObj));
      const header = new Uint8Array(2);
      ghiVarint(header, payloadBuf.byteLength);
      const total = new Uint8Array(header.byteLength + payloadBuf.byteLength);
      total.set(header, 0);
      total.set(payloadBuf, header.byteLength);
      return total;
    }

    function dungPublish(topic, payloadObj) {
      return bocPublish(topic, payloadObj);
    }
  } catch (_) {}
})();