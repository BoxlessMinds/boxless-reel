/**
 * TypeScript interfaces matching the FastAPI backend Pydantic schemas.
 * Uses snake_case to match API responses directly.
 */

// Transcript types
export interface TranscriptSegment {
  text: string;
  start: number;
  duration: number;
}

export interface Transcript {
  id: string;
  video_id: string;
  title: string;
  channel_name: string | null;
  thumbnail_url: string | null;
  transcript_text: string;
  transcript_segments: TranscriptSegment[];
  language: string;
  duration_seconds: number | null;
  created_at: string;
  updated_at: string;
}

export interface TranscriptListItem {
  id: string;
  video_id: string;
  title: string;
  channel_name: string | null;
  thumbnail_url: string | null;
  language: string;
  duration_seconds: number | null;
  created_at: string;
}

export interface TranscriptListResponse {
  items: TranscriptListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface TranscriptExtractRequest {
  youtube_url: string;
}

// Document types
export interface Document {
  id: string;
  session_id: string;
  original_filename: string;
  file_type: string;
  file_size: number;
  page_count: number | null;
  word_count: number | null;
  is_indexed: boolean;
  created_at: string;
}

export interface SessionDocumentsResponse {
  session_id: string;
  documents: Document[];
  count: number;
  max_documents: number;
  can_add_more: boolean;
}

export interface DocumentListResponse {
  items: Document[];
  total: number;
  skip: number;
  limit: number;
}

export interface DocumentListParams {
  skip?: number;
  limit?: number;
  search?: string;
}

// Session/Query types
export interface Citation {
  text: string;
  source_type: 'transcript' | 'document' | 'web';

  // Transcript citations
  start_time?: number;
  end_time?: number | null;
  timestamp_formatted?: string;

  // Web citations
  url?: string;
  title?: string;

  // Document citations
  document_id?: string;
  document_name?: string;
  page_number?: number;
}

export interface QueryResponse {
  content: string;
  citations: Citation[];
  session_id: string;
  model_used: string;
  search_results_used: number;
  created_at: string;
}

export interface Session {
  session_id: string;
  transcript_id: string;
  video_id: string;
  video_title: string;
  thumbnail_url: string | null;
  model_provider: string;
  model_id: string;
  created_at: string;
  last_activity: string;
  query_count: number;
}

export interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  citations: Citation[] | null;
}

export interface SessionDetail extends Session {
  messages: Message[];
}

export interface SessionListResponse {
  items: Session[];
  total: number;
}

// Error types
export interface ApiErrorResponse {
  detail: string;
}

// Settings types
export interface ProviderModels {
  provider: 'anthropic' | 'openai';
  models: string[];
}

export interface LLMSettings {
  anthropic_api_key_configured: boolean;
  openai_api_key_configured: boolean;
  default_provider: 'anthropic' | 'openai';
  default_model: string;
  available_providers: string[];
  available_models: ProviderModels[];
  embedding_model: string;
  max_context_chunks: number;
  chunk_size: number;
  chunk_overlap: number;
  tavily_api_key_configured: boolean;
  web_search_enabled: boolean;
  web_search_max_results: number;
}

export interface LLMSettingsUpdate {
  anthropic_api_key?: string;
  openai_api_key?: string;
  default_provider?: 'anthropic' | 'openai';
  default_model?: string;
  embedding_model?: string;
  max_context_chunks?: number;
  chunk_size?: number;
  chunk_overlap?: number;
  tavily_api_key?: string;
  web_search_enabled?: boolean;
  web_search_max_results?: number;
}

export interface ValidateKeyRequest {
  provider: 'anthropic' | 'openai';
  api_key: string;
}

export interface ValidateKeyResponse {
  valid: boolean;
  error: string | null;
}

// Auth types
export type UserRole = 'admin' | 'user';

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface RefreshTokenRequest {
  refresh_token: string;
}

export interface RegisterRequest {
  token?: string;
  email: string;
  password: string;
  display_name: string;
}

export interface RegistrationMode {
  require_invitation: boolean;
}

export interface UserUpdateRequest {
  display_name?: string;
  current_password?: string;
  new_password?: string;
}

export interface AdminUserUpdateRequest {
  is_active?: boolean;
  role?: UserRole;
}

export interface UserListResponse {
  items: User[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// Invitation types
export type InvitationStatus = 'pending' | 'accepted' | 'expired' | 'revoked';

export interface Invitation {
  id: string;
  email: string;
  status: InvitationStatus;
  expires_at: string;
  created_at: string;
  invite_link?: string | null;
}

export interface InvitationCreateRequest {
  email: string;
}

export interface InvitationListResponse {
  items: Invitation[];
  total: number;
}

export interface InvitationValidateResponse {
  valid: boolean;
  email?: string | null;
  expires_at?: string | null;
  error?: string | null;
}

export interface BulkInvitationRequest {
  emails: string[];
}

export interface BulkInvitationResponse {
  created: string[];
  failed: { email: string; reason: string }[];
}

// Playlist types
export interface Playlist {
  id: string;
  youtube_playlist_id: string;
  title: string;
  description: string | null;
  privacy_status: string;
  item_count: number;
  duplicate_count: number;
  unavailable_count: number;
  is_owned: boolean;
  last_synced_at: string;
}

export interface PlaylistListResponse {
  items: Playlist[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export type PlaylistItemAvailability = 'available' | 'private' | 'deleted' | 'unknown';

export interface PlaylistItem {
  id: string;
  youtube_playlist_item_id: string;
  video_id: string;
  title: string | null;
  channel_title: string | null;
  position: number;
  availability: PlaylistItemAvailability;
  published_at: string | null;
  added_at: string | null;
}

export interface PlaylistItemListResponse {
  items: PlaylistItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface PlaylistSyncResponse {
  playlists_synced: number;
  items_synced: number;
  quota_units_used: number;
  synced_at: string;
}

// Cross-Chat types
export interface CrossChatSessionSummary {
  session_id: string;
  transcript_id: string;
  video_id: string;
  video_title: string;
  thumbnail_url: string | null;
}

export interface CrossChatSession {
  id: string;
  referenced_sessions: CrossChatSessionSummary[];
  model_provider: string;
  model_name: string;
  created_at: string;
  last_activity: string;
  query_count: number;
}

export interface CrossChatSessionDetail extends CrossChatSession {
  messages: Message[];
}

export interface CrossChatSessionListResponse {
  items: CrossChatSession[];
  total: number;
}

export interface CrossChatQueryResponse {
  content: string;
  citations: Citation[];
  session_id: string;
  model_used: string;
  search_results_used: number;
  created_at: string;
}

// Plan/apply engine types
export type PlanOpStatus = 'pending' | 'done' | 'skipped' | 'failed';
export type PlanStatus = 'pending' | 'applying' | 'done' | 'failed';

export interface PlanOp {
  id: string;
  sequence: number;
  op_type: string;
  status: PlanOpStatus;
  payload: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  depends_on_sequence: number | null;
  estimated_units: number;
  actual_units: number | null;
  error_message: string | null;
  executed_at: string | null;
}

export interface Plan {
  id: string;
  user_id: string;
  kind: string;
  status: PlanStatus;
  params: Record<string, unknown> | null;
  budget_units: number | null;
  created_at: string;
  updated_at: string;
  ops: PlanOp[];
  total_estimated_units: number;
  total_actual_units: number;
}

export interface ApplyPlanRequest {
  budget_units?: number | null;
}

export interface CreatePlanRequestCreate {
  kind: 'create';
  title: string;
  description: string | null;
  privacy_status: string;
}

export interface CreatePlanRequestDedupe {
  kind: 'dedupe';
  playlist_id: string;
}

export type PurgeUnavailableMode = 'deleted' | 'deleted_and_private';

export interface CreatePlanRequestPurgeUnavailable {
  kind: 'purge_unavailable';
  playlist_id: string;
  mode?: PurgeUnavailableMode;
  enrich?: boolean;
}

export interface CreatePlanRequestCopy {
  kind: 'copy';
  source_playlist_ids: string[];
  target_playlist_id: string | null;
  target_title: string | null;
  filter_regex: string | null;
  force_new: boolean;
}

export interface CreatePlanRequestAddUrl {
  kind: 'add_url';
  urls: string[];
  target_playlist_id: string | null;
  target_title: string | null;
}

export interface CreatePlanRequestPurgeWatched {
  kind: 'purge_watched';
  playlist_id: string;
  watched_before?: string | null;
}

export interface CreatePlanRequestMove {
  kind: 'move';
  source_playlist_id: string;
  target_playlist_id: string;
  filter_regex: string | null;
}

export type ReorderSortBy = 'title' | 'channel' | 'published' | 'added';

export interface CreatePlanRequestReorder {
  kind: 'reorder';
  playlist_id: string;
  sort_by: ReorderSortBy;
}

export type CreatePlanRequest =
  | CreatePlanRequestCreate
  | CreatePlanRequestDedupe
  | CreatePlanRequestPurgeUnavailable
  | CreatePlanRequestCopy
  | CreatePlanRequestAddUrl
  | CreatePlanRequestPurgeWatched
  | CreatePlanRequestMove
  | CreatePlanRequestReorder;

/** One dry-run removal candidate surfaced in a dedupe/purge_unavailable
 * plan's `params.removals` -- see `Plan.params`. */
export interface PlanRemovalCandidate {
  sequence: number;
  video_id: string;
  title: string | null;
  position: number;
}

export interface QuotaResponse {
  daily_limit: number;
  used: number;
  remaining: number;
}

// Watch history import types
export interface WatchHistoryImport {
  id: string;
  user_id: string;
  original_filename: string;
  status: string;
  entry_count: number;
  imported_at: string;
  created_at: string;
}

export interface WatchHistoryImportListResponse {
  items: WatchHistoryImport[];
  total: number;
  skip: number;
  limit: number;
}

export interface WatchHistoryListParams {
  skip?: number;
  limit?: number;
}
