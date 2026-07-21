// Navigation channel: StreamDeck's app pushes {type:"navigate", url} over a
// WebSocket when Play is clicked; we point the active tab at it. The app also
// pings every ~20s, which keeps this MV3 service worker alive; an alarm
// reconnects if the socket (or the worker) ever drops.
const WS_URL = 'ws://app:8000/ws/nav';
let ws = null;

function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  try {
    ws = new WebSocket(WS_URL);
  } catch (e) {
    ws = null;
    return;
  }
  ws.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    if (msg.type === 'navigate' && typeof msg.url === 'string' && /^https?:\/\//.test(msg.url)) {
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs && tabs[0]) chrome.tabs.update(tabs[0].id, { url: msg.url });
        else chrome.tabs.create({ url: msg.url });
      });
    }
  };
  ws.onclose = () => { ws = null; };
  ws.onerror = () => { try { ws.close(); } catch {} };
}

chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
chrome.alarms.create('reconnect', { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(connect);
connect();
