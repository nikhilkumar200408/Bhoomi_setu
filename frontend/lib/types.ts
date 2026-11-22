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
  land_record_id?: string | null;
}

export interface ExtractedField {
  id: string;
  field_name: string;
  value: string | null;
  confidence: number;
  ocr_confidence: number;
  extraction_confidence: number;
  confidence_band: "HIGH" | "REVIEW" | "VERIFY";
  source_page: number | null;
  source_bbox: number[] | null;
  source_text: string | null;
  review_reason: string | null;
  validation_status: string;
}

export interface ValidationResultItem {
  id: string;
  rule: string;
  status: "PASS" | "WARNING" | "FAIL";
  severity: "LOW" | "MEDIUM" | "HIGH";
  message: string;
  affected_field: string | null;
}

export interface LandRecord {
  id: string;
  document_id: string;
  status: "PENDING_REVIEW" | "AUTO_PASSED" | "VERIFIED" | "REJECTED" | "UNRESOLVED";
  overall_confidence: number;
  anomaly_score: number;
  anomaly_level: "LOW" | "MEDIUM" | "HIGH";
  anomaly_reasons: string[];
  created_at: string;
  verified_at: string | null;
  verified_by: string | null;
  signature_hash: string | null;
}

export interface LandRecordDetail extends LandRecord {
  fields: ExtractedField[];
  validations: ValidationResultItem[];
  document: DocumentItem;
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

export interface DashboardStats {
  documents_processed: number;
  records_extracted: number;
  pending_verification: number;
  average_confidence: number;
  auto_processed_pct: number;
  human_review_pct: number;
  validation_warnings: number;
  average_processing_time_seconds: number;
  confidence_distribution: Record<string, number>;
  validation_error_categories: Record<string, number>;
  verification_status_breakdown: Record<string, number>;
  district_wise_progress: Record<string, number>;
  is_synthetic: boolean;
}

export interface SearchResultItem {
  record_id: string;
  document_id: string;
  owner_name: string | null;
  survey_number: string | null;
  khasra_number: string | null;
  khata_number: string | null;
  village: string | null;
  tehsil: string | null;
  district: string | null;
  status: string;
  overall_confidence: number;
}

export interface OfficerQueueItem {
  record_id: string;
  document_id: string;
  owner_name: string | null;
  survey_number: string | null;
  village: string | null;
  district: string | null;
  status: string;
  overall_confidence: number;
  anomaly_level: "LOW" | "MEDIUM" | "HIGH";
  anomaly_reasons: string[];
  created_at: string;
}

export interface UserActivityItem {
  user_id: string;
  username: string;
  full_name: string;
  role: UserRole;
  action_count: number;
  last_action_at: string | null;
}
