export type UserRole = "student" | "faculty" | "admin";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
}

export interface AccessTokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface Course {
  id: string;
  name: string;
  code: string;
  created_by_id: string;
  is_active: boolean;
  created_at: string;
  faculty_name?: string | null;
  description?: string | null;
}

export interface Enrollment {
  id: string;
  course_id: string;
  user_id: string;
  role: "student" | "faculty";
  created_at: string;
}

export interface Essay {
  id: string;
  student_id: string;
  course_id: string | null;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  parse_status: "parsed" | "failed";
  normalizer_version: string;
  page_map: PageMetadata[];
  extractor_name: string;
  extractor_version: string;
  sha256: string;
  created_at: string;
}

export interface PageMetadata {
  page_number: number | null;
  extracted_char_start: number;
  extracted_char_end: number;
  normalized_char_start: number;
  normalized_char_end: number;
  extraction_method: "native" | "ocr";
  ocr_confidence: number | null;
}

export interface EssayText {
  extracted_text: string;
  normalized_text: string;
  normalizer_version: string;
  offset_alignment: number[][];
  page_map: PageMetadata[];
}

export interface Rubric {
  id: string;
  course_id: string;
  created_by_id: string;
  title: string;
  description: string | null;
  status: "draft" | "published" | "archived";
  created_at: string;
}

export interface RubricCriterion {
  id: string;
  rubric_version_id: string;
  name: string;
  description: string;
  levels: { score: string; description: string }[];
  min_score: string;
  max_score: string;
  weight: string;
  sort_order: number;
}

export interface RubricCriterionInput {
  name: string;
  description: string;
  levels: { score: string; description: string }[];
  min_score: string;
  max_score: string;
  weight: string;
  sort_order: number;
}

export interface RubricVersion {
  id: string;
  rubric_id: string;
  version_number: number;
  is_published: boolean;
  published_at: string | null;
  snapshot: Record<string, unknown> | null;
  criteria: RubricCriterion[];
}

export type EvaluationStatus =
  | "queued"
  | "running"
  | "needs_review"
  | "approved"
  | "rejected"
  | "changes_requested"
  | "failed";

export interface EvidenceQuote {
  source_chunk_id: string;
  quoted_text: string;
  model_relevance_rationale: string;
  existence_status: "verified";
  relevance_status: "unverified";
  extracted_char_start: number;
  extracted_char_end: number;
  normalized_char_start: number;
  normalized_char_end: number;
  paragraph_start: number | null;
  paragraph_end: number | null;
  page_start: number | null;
  page_end: number | null;
}

export interface Claim {
  text: string;
  evidence_quotes: EvidenceQuote[];
}

export interface CriterionScore {
  id: string;
  criterion_id: string;
  ai_score: string;
  ai_rationale: string;
  strengths: string[];
  weaknesses: string[];
  suggestions: string[];
  claims: Claim[];
  faculty_score: string | null;
  faculty_rationale: string | null;
  faculty_strengths: string[] | null;
  faculty_weaknesses: string[] | null;
  faculty_suggestions: string[] | null;
}

export type ReviewAction =
  | "note_added"
  | "criterion_updated"
  | "approved"
  | "rejected"
  | "changes_requested";

export interface ReviewEvent {
  id: string;
  faculty_id: string;
  criterion_score_id: string | null;
  action: ReviewAction;
  notes: string | null;
  created_at: string;
}

export interface Evaluation {
  id: string;
  essay_id: string;
  rubric_version_id: string;
  requested_by_id: string;
  evaluation_mode: "openai" | "mock";
  status: EvaluationStatus;
  ai_total_score: string | null;
  faculty_total_score: string | null;
  has_unsupported_flags: boolean;
  error_code: string | null;
  started_at: string;
  completed_at: string | null;
  criterion_scores: CriterionScore[];
  review_history: ReviewEvent[];
}

export interface ReviewQueueItem {
  evaluation_id: string;
  essay_id: string;
  student_id: string;
  course_id: string;
  rubric_version_id: string;
  evaluation_mode: "openai" | "mock";
  status: "needs_review" | "changes_requested";
  started_at: string;
  completed_at: string | null;
}

export interface DemoPageMetadata {
  page_number: number | null;
  extracted_char_start: number;
  extracted_char_end: number;
  extraction_method: "native" | "ocr";
}

export interface DemoEvidenceQuote {
  quoted_text: string;
  extracted_char_start: number;
  extracted_char_end: number;
  page_number: number | null;
  existence_verified: boolean;
}

export interface DemoCriterionResult {
  name: string;
  description: string;
  weight_percent: number;
  score: number;
  max_score: number;
  weighted_score: number;
  basis: string;
  strengths: string[];
  areas_to_improve: string[];
  suggestions: string[];
  evidence_quotes: DemoEvidenceQuote[];
}

export interface DemoEvaluation {
  id: string;
  filename: string;
  created_at: string;
  evaluation_mode: "local_demo";
  demo_label: "DEMO-GENERATED — NOT AI";
  status: "needs_review" | "changes_requested" | "approved";
  extracted_text: string;
  extractor_name: string;
  page_map: DemoPageMetadata[];
  total_score: number;
  max_total_score: number;
  criteria: DemoCriterionResult[];
  faculty_note: string | null;
}
