import axios from "axios";

export const API_ROOT = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL: `${API_ROOT}/api`,
});

export function adminHeaders(adminApiKey) {
  return {
    headers: {
      "X-Admin-API-Key": adminApiKey,
    },
  };
}

export async function getGraph() {
  const response = await api.get("/graph");
  return response.data;
}

export async function getFaultList(query = "", limit = 200) {
  const response = await api.get("/graph/faults", {
    params: { q: query, limit },
  });
  return response.data;
}

export async function getFaultGraph(faultId) {
  const response = await api.get(`/graph/fault/${encodeURIComponent(faultId)}`);
  return response.data;
}

export async function searchGraph(query) {
  const response = await api.get("/graph/search", {
    params: { q: query },
  });
  return response.data;
}

export async function getGraphStats() {
  const response = await api.get("/graph/stats");
  return response.data;
}
