export type TenderStatus = "created" | "in_review" | "analyzed" | "failed" | string;

export interface User {
  id: string;
  full_name: string;
  email: string;
  created_at?: string;
  updated_at?: string;
}

export interface RegisterPayload {
  full_name: string;
  email: string;
  password: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type?: string;
}

export interface HealthResponse {
  status?: string;
  message?: string;
  [key: string]: unknown;
}

export interface CreateTenderPayload {
  title: string;
  customer_name: string;
  description: string;
}

export interface TenderDocument {
  id?: string;
  filename?: string;
  original_filename?: string;
  name?: string;
  content_type?: string;
  mime_type?: string;
  file_size?: number;
  size?: number;
  uploaded_at?: string;
  created_at?: string;
  path?: string;
  [key: string]: unknown;
}

export interface ReportPayload {
  report?: Record<string, unknown>;
  risk?: Record<string, unknown>;
  documents?: TenderDocument[] | Record<string, unknown>[];
  [key: string]: unknown;
}

export interface Tender {
  id: string;
  owner_id?: string;
  title: string;
  customer_name: string;
  description?: string;
  status: TenderStatus;
  tender_risk_score?: number | null;
  analysis_summary?: string | null;
  extracted_requirements?: unknown;
  report_payload?: ReportPayload | null;

  report_docx_filename?: string | null;
  report_docx_generated_at?: string | null;


  documents?: TenderDocument[];
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface ApiMessageResponse {
  message?: string;
  detail?: string;
  [key: string]: unknown;
}

export interface AuthContextValue {
  user: User | null;
  token: string | null;
  loading: boolean;
  isAuthenticated: boolean;
  login: (payload: LoginPayload) => Promise<User>;
  register: (payload: RegisterPayload) => Promise<unknown>;
  logout: () => void;
  refreshUser: (tokenOverride?: string) => Promise<User>;
}