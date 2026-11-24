export type UserRole = "ADMIN" | "DATA_ENTRY_OPERATOR" | "REVENUE_OFFICER";

export interface User {
  id: string;
  username: string;
  full_name: string;
  role: UserRole;
}

export interface DocumentItem {
  id: string;
  filename: string;
  file_type: string;
  file_size_bytes: number;
  status: "UPLOADED" | "PROCESSING" | "PROCESSED" | "FAILED";
  uploaded_at: string;
  processed_at?: string | null;
  error_message?: string | null;
}

export interface ExtractedField {
  id: string;
  field_name: string;
  value: string | null;
  source_page: number | null;
  source_text: string | null;
  ocr_confidence: number;
  extraction_confidence: number;
  review_reason?: string | null;
  source_bbox?: [number, number, number, number] | null;
}

export interface AuditLogItem {
  id: string;
  record_id: string | null;
  document_id: string | null;
  action: string;
  user_id: string | null;
  old_value: string | null;
  new_value: string | null;
  log_metadata: Record<string, unknown>;
  timestamp: string;
}

export interface UserActivityItem {
  user_id: string;
  username: string;
  full_name: string;
  role: UserRole;
  action_count: number;
  last_action_at: string | null;
}
