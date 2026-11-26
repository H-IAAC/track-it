/* ws_client.js — progress WebSocket. Dispatches messages by `type`. */
const WSClient = (() => {
  let sock = null;
  let curId = null;
  const handlers = {}; // type -> [fn]

  function on(type, fn) { (handlers[type] ||= []).push(fn); }

  function dispatch(msg) {
    (handlers[msg.type] || []).forEach((fn) => {
      try { fn(msg); } catch (e) { console.error("ws handler", e); }
    });
  }

  function connect(videoId) {
    if (curId === videoId && sock && sock.readyState <= 1) return;
    disconnect();
    curId = videoId;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const encId = String(videoId).split("/").map(encodeURIComponent).join("/");
    sock = new WebSocket(`${proto}://${location.host}/ws/progress/${encId}`);
    sock.onmessage = (ev) => {
      let data; try { data = JSON.parse(ev.data); } catch (_) { return; }
      if (data && data.type) dispatch(data);
    };
    sock.onclose = () => { if (sock) sock = null; };
    sock.onerror = () => {};
  }

  function disconnect() {
    if (sock) { try { sock.close(); } catch (_) {} sock = null; }
    curId = null;
  }

  return { on, connect, disconnect, get id() { return curId; } };
})();
