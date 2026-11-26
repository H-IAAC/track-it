/* api.js — thin REST wrapper over the FastAPI backend. Throws on !ok. */
const API = (() => {
  async function req(method, path, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(path, opts);
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch (_) {}
      const err = new Error(`${res.status} ${detail}`);
      err.status = res.status;
      throw err;
    }
    const ct = res.headers.get("content-type") || "";
    return ct.includes("application/json") ? res.json() : res.text();
  }

  // ids can be nested paths ("subA/clip") — encode each segment, keep slashes
  const enc = (id) => String(id).split("/").map(encodeURIComponent).join("/");

  async function uploadReq(path, file) {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(path, { method: "POST", body: formData });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  }

  return {
    uploadVideo: (file)          => uploadReq("/api/upload", file),
    getConfig:   ()              => req("GET",  "/api/config"),
    listVideos:  ()              => req("GET",  "/api/videos"),
    listSessions:()              => req("GET",  "/api/sessions"),
    metadata:    (id)            => req("GET",  `/api/video/${enc(id)}/metadata`),
    fileUrl:     (id)            => `/api/video/${enc(id)}/file?t=${Date.now()}`,

    track:       (id, p)         => req("POST", `/api/video/${enc(id)}/track`, p),
    cancelTrack: (id)            => req("POST", `/api/video/${enc(id)}/track/cancel`),

    getMasks:    (id, pass)      => req("GET",  `/api/video/${enc(id)}/masks/${pass}`),
    saveMasks:   (id, pass, jl)  => req("POST", `/api/video/${enc(id)}/masks/${pass}`, { jsonl: jl }),

    advance:     (id)            => req("POST", `/api/video/${enc(id)}/advance`),
    render:      (id, p)         => req("POST", `/api/video/${enc(id)}/render`, p),
    getOutputs:  (id)            => req("GET",  `/api/video/${enc(id)}/outputs`),
    outputUrl:   (id, pass)      => `/api/video/${enc(id)}/output/${pass}`,
  };
})();
