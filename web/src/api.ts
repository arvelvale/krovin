import type {
  IntegrationsView, LinearDiscover, MemoryItem, ModelsView, ProviderInput, SessionDetail, SessionSummary, Slot, SlotRef,
  Status, WsChanges, WsEntry, WsFile, WsListing,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown, raw?: Blob): Promise<T> {
  const init: RequestInit = { method, credentials: "same-origin", headers: {} };
  if (raw) {
    init.body = raw;
    (init.headers as Record<string, string>)["Content-Type"] = raw.type || "application/octet-stream";
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  let resp: Response;
  try {
    resp = await fetch(path, init);
  } catch {
    throw new ApiError(0, "连不上面板后端，看看节点上的服务还在不在");
  }
  const text = await resp.text();
  const data = text ? safeJson(text) : null;
  if (!resp.ok) {
    const msg = (data && typeof data === "object" && "error" in data ? String(data.error) : "") || `请求失败（${resp.status}）`;
    if (resp.status === 401 && path !== "/api/login") window.dispatchEvent(new Event("dgx:unauthorized"));
    throw new ApiError(resp.status, msg);
  }
  return data as T;
}

function safeJson(text: string): any {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export const api = {
  login: (token: string) => request<{ ok: boolean }>("POST", "/api/login", { token }),
  logout: () => request<{ ok: boolean }>("POST", "/api/logout", {}),
  status: () => request<Status>("GET", "/api/status"),
  sessions: () => request<SessionSummary[]>("GET", "/api/sessions"),
  createSession: (useJev: boolean, tier: string, yolo = false, bypass = false) =>
    request<{ id: string }>("POST", "/api/sessions", { use_jev: useJev, tier, yolo, bypass }),
  renameSession: (id: string, title: string) =>
    request<{ ok: boolean; title: string }>("PATCH", `/api/sessions/${encodeURIComponent(id)}`, { title }),
  sessionCleanup: (id: string) => request<{ description: string; delete_workspace: boolean }>("GET", `/api/sessions/${encodeURIComponent(id)}/cleanup`),
  deleteSession: (id: string, deleteWorkspace?: boolean) => request<{ ok: boolean; workspace_deleted: boolean }>("DELETE", `/api/sessions/${encodeURIComponent(id)}`, { delete_workspace: deleteWorkspace }),
  setYolo: (id: string, yolo: boolean, bypass = false) =>
    request<{ tier: string; yolo: boolean; bypass: boolean }>("PATCH", `/api/sessions/${encodeURIComponent(id)}`, { yolo, bypass }),
  session: (id: string) => request<SessionDetail>("GET", `/api/sessions/${encodeURIComponent(id)}`),
  resumeSession: (id: string) => request<{ id: string }>("POST", `/api/sessions/${encodeURIComponent(id)}/resume`, {}),
  setTier: (id: string, tier: string) =>
    request<{ tier: string }>("PATCH", `/api/sessions/${encodeURIComponent(id)}`, { tier }),
  uploadImage: (id: string, file: File) =>
    request<{ id: string; mime: string }>("POST", `/api/sessions/${encodeURIComponent(id)}/images`, undefined, file),
  imageUrl: (id: string, imageId: string) =>
    `/api/sessions/${encodeURIComponent(id)}/images/${encodeURIComponent(imageId)}`,
  turn: (id: string, text: string, source: "text" | "voice", images: string[] = []) =>
    request<{ ok: boolean }>("POST", `/api/sessions/${encodeURIComponent(id)}/turn`, { text, source, images }),
  confirm: (id: string, confirmId: string, approve: boolean) =>
    request<{ ok: boolean }>("POST", `/api/sessions/${encodeURIComponent(id)}/confirm`, { id: confirmId, approve }),
  stop: (id: string) =>
    request<{ ok: boolean; stopped: boolean }>("POST", `/api/sessions/${encodeURIComponent(id)}/stop`, {}),
  memory: (status: "active" | "pending") => request<MemoryItem[]>("GET", `/api/memory?status=${status}`),
  approveMemory: (id: string) => request<{ ok: boolean }>("POST", `/api/memory/${encodeURIComponent(id)}/approve`, {}),
  forgetMemory: (id: string) => request<{ ok: boolean }>("DELETE", `/api/memory/${encodeURIComponent(id)}`),
  resetDemo: () => request<{ ok: boolean; workspace: string }>("POST", "/api/demo/reset", {}),
  models: () => request<ModelsView>("GET", "/api/models"),
  setSlots: (slots: Partial<Record<Slot, SlotRef>>) => request<ModelsView>("PUT", "/api/models/slots", slots),
  saveProvider: (id: string, body: ProviderInput) =>
    request<ModelsView>("PUT", `/api/models/providers/${encodeURIComponent(id)}`, body),
  deleteProvider: (id: string) => request<ModelsView>("DELETE", `/api/models/providers/${encodeURIComponent(id)}`),
  discoverModels: (id: string) =>
    request<{ models: string[] }>("POST", `/api/models/providers/${encodeURIComponent(id)}/discover`, {}),
  testModel: (id: string, model: string) =>
    request<{ ok: boolean; latency_ms?: number; reply?: string; error?: string }>(
      "POST", `/api/models/providers/${encodeURIComponent(id)}/test`, { model }),
  workspaces: () => request<WsListing>("GET", "/api/workspaces"),
  createWorkspace: (body: { name: string; kind: string; mode: "empty" | "clone"; url?: string; branch?: string }) =>
    request<WsListing>("POST", "/api/workspaces", body),
  uploadZip: (name: string, kind: string, zip: Blob) =>
    request<WsListing>("POST", `/api/workspaces/upload?name=${encodeURIComponent(name)}&kind=${kind}`, undefined, zip),
  beginFolder: (name: string, kind: string) =>
    request<{ id: string }>("POST", `/api/workspaces/folder?name=${encodeURIComponent(name)}&kind=${kind}`, {}),
  putFile: (id: string, path: string, blob: Blob) =>
    request<{ ok: boolean }>("PUT", `/api/workspaces/${id}/file?path=${encodeURIComponent(path)}`, undefined, blob),
  finishFolder: (id: string) => request<WsListing>("POST", `/api/workspaces/${id}/finish`, {}),
  activateWorkspace: (id: string) => request<WsListing>("POST", `/api/workspaces/${id}/activate`, {}),
  pullWorkspace: (id: string) => request<WsListing>("POST", `/api/workspaces/${id}/pull`, {}),
  deleteWorkspace: (id: string) => request<WsListing>("DELETE", `/api/workspaces/${id}`),
  wsTree: (id: string, path: string) =>
    request<{ entries: WsEntry[] }>("GET", `/api/workspaces/${id}/tree?path=${encodeURIComponent(path)}`),
  wsFile: (id: string, path: string) =>
    request<WsFile>("GET", `/api/workspaces/${id}/file?path=${encodeURIComponent(path)}`),
  wsChanges: (id: string) => request<WsChanges>("GET", `/api/workspaces/${id}/changes`),
  wsRaw: async (id: string, path: string): Promise<Blob> => {
    const r = await fetch(`/api/workspaces/${id}/raw?path=${encodeURIComponent(path)}`, { credentials: "same-origin" });
    if (!r.ok) throw new ApiError(r.status, "读取文件失败");
    return r.blob();
  },
  startPreview: (id: string, path = "/") =>
    request<{ url: string; kind: string; expires_in: number }>("POST", `/api/workspaces/${id}/live-preview`, { path }),
  stopPreview: (id: string) => request<{ ok: boolean }>("DELETE", `/api/workspaces/${id}/live-preview`, {}),
  previewWorkspace: (id: string) =>
    request<{ url: string; expires_in: number }>("POST", `/api/workspaces/${id}/preview`, {}),
  wsZipUrl: (id: string) => `/api/workspaces/${id}/zip`,
  integrations: () => request<IntegrationsView>("GET", "/api/integrations"),
  discoverLinear: (apiKey: string) => request<LinearDiscover>("POST", "/api/integrations/linear/discover", { api_key: apiKey }),
  saveLinear: (body: { api_key?: string; team_key: string; project_name: string }) =>
    request<IntegrationsView>("PUT", "/api/integrations/linear", body),
  clearLinear: () => request<IntegrationsView>("DELETE", "/api/integrations/linear"),
  saveGit: (name: string, email: string) =>
    request<IntegrationsView>("PUT", "/api/integrations/git", { user_name: name, user_email: email }),
  saveToken: (host: string, token: string) =>
    request<IntegrationsView>("PUT", `/api/integrations/git/tokens/${encodeURIComponent(host)}`, { token }),
  deleteToken: (host: string) =>
    request<IntegrationsView>("DELETE", `/api/integrations/git/tokens/${encodeURIComponent(host)}`),
  setOnboarded: (done: boolean) => request<IntegrationsView>("PUT", "/api/integrations/onboarded", { done }),
  asr: (wav: Blob) => request<{ text: string }>("POST", "/api/asr?format=wav", undefined, wav),
  streamUrl: (id: string) => `/api/sessions/${encodeURIComponent(id)}/stream`,
};
