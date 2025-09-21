// Centralized API helper for FastAPI backend
// Base URL from env or default localhost
const BASE_URL = (process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");

function authHeaders() {
  const token = typeof window !== "undefined" ? localStorage.getItem("bearer_token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function handleJSON<T>(res: Response): Promise<T> {
  if (res.ok) return (await res.json()) as T;
  let msg = `Request failed (${res.status})`;
  try {
    const data = await res.json();
    // Common FastAPI error shapes
    msg = (data?.detail as string) || data?.message || msg;
  } catch {
    try {
      const text = await res.text();
      if (text) msg = text;
    } catch {}
  }
  throw new Error(msg);
}

export async function createUser(email: string): Promise<{ id: string; email: string; created_at?: string }>
{
  const res = await fetch(`${BASE_URL}/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ email }),
  });
  return handleJSON(res);
}

export async function getUsage(userId: string): Promise<{ scenarios_run: number; reports_exported: number }>
{
  const res = await fetch(`${BASE_URL}/users/${encodeURIComponent(userId)}/usage`, {
    headers: { ...authHeaders() },
    cache: "no-store",
  });
  return handleJSON(res);
}

export interface SimulatePayload {
  user_id: string;
  employees: number;
  salary_per_employee: number; // FastAPI expects salary_per_employee
  marketing_spend: number;     // FastAPI expects marketing_spend
  product_price: number;       // FastAPI expects product_price
}

export interface SimulateResponse {
  scenario: {
    id: string;
    user_id: string;
    employees: number;
    salary_per_employee: number;
    marketing_spend: number;
    product_price: number;
    forecast_summary: string;
    created_at?: string;
  };
  usage: { scenarios_run: number; reports_exported: number };
}

export async function simulateScenario(payload: SimulatePayload): Promise<SimulateResponse> {
  const res = await fetch(`${BASE_URL}/scenarios/simulate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  return handleJSON(res);
}

export interface ExportReportPayload {
  user_id: string;
  report_type: "pdf" | "docx";
  scenario_id?: string | null;
}

export interface FileDownload {
  blob: Blob;
  filename: string;
}

export async function exportReport(payload: ExportReportPayload): Promise<FileDownload> {
  const res = await fetch(`${BASE_URL}/reports/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    // Try to parse error
    try {
      const data = await res.json();
      throw new Error((data?.detail as string) || data?.message || `Export failed (${res.status})`);
    } catch (e:any) {
      if (e instanceof Error) throw e;
      const text = await res.text();
      throw new Error(text || `Export failed (${res.status})`);
    }
  }

  const blob = await res.blob();
  // Try to get a filename from Content-Disposition
  const cd = res.headers.get("Content-Disposition") || res.headers.get("content-disposition");
  let filename = "report";
  if (cd) {
    const match = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(cd);
    const name = decodeURIComponent(match?.[1] || match?.[2] || "");
    if (name) filename = name;
  }
  // Fallback extension by report_type when not provided via headers
  if (!/\.(pdf|docx)$/i.test(filename)) {
    const ext = payload.report_type === "pdf" ? "pdf" : "docx";
    filename = `${filename}.${ext}`;
  }
  return { blob, filename };
}

export async function getScenario(id: string) {
  const res = await fetch(`${BASE_URL}/scenarios/${encodeURIComponent(id)}`, { headers: { ...authHeaders() } });
  return handleJSON<any>(res);
}

export async function getReport(id: string) {
  const res = await fetch(`${BASE_URL}/reports/${encodeURIComponent(id)}`, { headers: { ...authHeaders() } });
  return handleJSON<any>(res);
}

export async function healthCheck(): Promise<{ status: string }> {
  const res = await fetch(`${BASE_URL}/health`, { headers: { ...authHeaders() }, cache: "no-store" });
  return handleJSON(res);
}

// Optional: pathway live polling helper (not required by spec, keeps component clean)
export async function getPathwayLive(): Promise<{ revenueDeltaPct?: number; customers?: number }>{
  const res = await fetch(`${BASE_URL}/pathway/live`, { headers: { ...authHeaders() }, cache: "no-store" });
  return handleJSON(res);
}

export { BASE_URL };