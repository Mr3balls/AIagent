import {
    ApiMessageResponse,
    CreateTenderPayload,
    HealthResponse,
    LoginPayload,
    LoginResponse,
    RegisterPayload,
    Tender,
    User,
  } from "@/lib/types";
  import { buildAuthHeader } from "@/lib/auth";
  import { isObject } from "@/lib/utils";
  
  const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  
  function getApiUrl(path: string): string {
    return `${API_BASE_URL}${path}`;
  }
  
  function parseErrorPayload(payload: unknown, fallbackMessage: string): string {
    if (typeof payload === "string" && payload.trim()) {
      return payload;
    }
  
    if (isObject(payload)) {
      const detail = payload.detail;
  
      if (typeof detail === "string" && detail.trim()) {
        return detail;
      }
  
      if (Array.isArray(detail)) {
        const messages = detail
          .map((item) => {
            if (typeof item === "string") {
              return item;
            }
  
            if (isObject(item) && typeof item.msg === "string") {
              return item.msg;
            }
  
            return "";
          })
          .filter(Boolean);
  
        if (messages.length > 0) {
          return messages.join(", ");
        }
      }
  
      if (typeof payload.message === "string" && payload.message.trim()) {
        return payload.message;
      }
    }
  
    return fallbackMessage;
  }
  
  async function apiRequest<T>(path: string, options: RequestInit = {}, token?: string | null): Promise<T> {
    const headers = new Headers(options.headers || {});
    const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
    const isUrlEncoded = options.body instanceof URLSearchParams;
  
    if (!isFormData && !isUrlEncoded && options.method && options.method !== "GET" && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
  
    const authHeaders = buildAuthHeader(token);
    Object.entries(authHeaders).forEach(([key, value]) => {
      headers.set(key, value);
    });
  
    const response = await fetch(getApiUrl(path), {
      ...options,
      headers,
      cache: "no-store",
    });
  
    if (!response.ok) {
      const fallbackMessage = `Request failed with status ${response.status}`;
      const rawErrorPayload = await response.text();
  
      if (!rawErrorPayload) {
        throw new Error(fallbackMessage);
      }
  
      try {
        const parsedPayload = JSON.parse(rawErrorPayload);
        throw new Error(parseErrorPayload(parsedPayload, fallbackMessage));
      } catch {
        throw new Error(parseErrorPayload(rawErrorPayload, fallbackMessage));
      }
    }
  
    const text = await response.text();
  
    if (!text) {
      return {} as T;
    }
  
    try {
      return JSON.parse(text) as T;
    } catch {
      return text as T;
    }
  }
  
  export async function getHealth(): Promise<HealthResponse> {
    return apiRequest<HealthResponse>("/health", {
      method: "GET",
    });
  }
  
  export async function registerUser(payload: RegisterPayload): Promise<ApiMessageResponse | User> {
    return apiRequest<ApiMessageResponse | User>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }
  
  export async function loginUser(payload: LoginPayload): Promise<LoginResponse> {
    const body = new URLSearchParams({
      username: payload.email,
      password: payload.password,
    });
  
    return apiRequest<LoginResponse>("/api/v1/auth/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body,
    });
  }
  
  export async function getMe(token: string): Promise<User> {
    return apiRequest<User>(
      "/api/v1/auth/me",
      {
        method: "GET",
      },
      token,
    );
  }
  
  export async function createTender(payload: CreateTenderPayload, token: string): Promise<Tender> {
    return apiRequest<Tender>(
      "/api/v1/tenders",
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
      token,
    );
  }
  
  export async function getTenders(token: string): Promise<Tender[]> {
    return apiRequest<Tender[]>(
      "/api/v1/tenders",
      {
        method: "GET",
      },
      token,
    );
  }
  
  export async function getTenderById(tenderId: string, token: string): Promise<Tender> {
    return apiRequest<Tender>(
      `/api/v1/tenders/${tenderId}`,
      {
        method: "GET",
      },
      token,
    );
  }
  
  export async function uploadTenderDocuments(tenderId: string, files: File[], token: string): Promise<Tender | ApiMessageResponse> {
    const formData = new FormData();
  
    files.forEach((file) => {
      formData.append("files", file);
    });
  
    return apiRequest<Tender | ApiMessageResponse>(
      `/api/v1/tenders/${tenderId}/upload`,
      {
        method: "POST",
        body: formData,
      },
      token,
    );
  }
  
  export async function analyzeTender(tenderId: string, token: string): Promise<Tender | ApiMessageResponse> {
    return apiRequest<Tender | ApiMessageResponse>(
      `/api/v1/tenders/${tenderId}/analyze`,
      {
        method: "POST",
      },
      token,
    );
  }