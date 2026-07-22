export interface FolderNode {
  id: string
  name: string
  path: string
  type: 'folder'
  children: FileNode[]
}

export interface FileLeafNode {
  id: string
  name: string
  path: string
  type: 'file'
  extension: string
  size: number
}

export type FileNode = FolderNode | FileLeafNode

export interface Course {
  id: string
  name: string
  path: string
  children: FileNode[]
  file_count: number
}

export interface Citation {
  source_type?: 'local' | 'web'
  reference_label?: string
  file_id: string
  file_name: string
  section_title?: string
  material_type?: string
  quote: string
  page: number | null
  chunk_index: number
  score: number
  url?: string
}

export interface TraceStep {
  label: string
  status: 'ok' | 'skip' | 'empty'
  detail: string
}

export interface Message {
  role: 'user' | 'assistant'
  content: string
  citations: Citation[]
  trace: TraceStep[]
  created_at: string
  streaming?: boolean
  stream_status?: string
}

export interface Note {
  id: number
  title: string
  content: string
  created_at: string
}

export interface StudyPlanItem {
  id: number
  title: string
  kind: 'read' | 'review' | 'practice'
  status: 'todo' | 'doing' | 'done'
  estimated_minutes: number
  source_file_id: string
  source_file_name: string
  created_at: string
  updated_at: string
  completed_at: string
}

export interface StudyPlanStats {
  total: number
  completed: number
  doing: number
  remaining_minutes: number
  progress_percent: number
  next_item_id: number | null
}

export interface StudyPlan {
  items: StudyPlanItem[]
  stats: StudyPlanStats
}

export interface KnowledgePoint {
  id: string
  title: string
  aliases: string[]
  source_refs: Array<Record<string, string>>
  created_at: string
  updated_at: string
}

export interface MasteryRecord {
  point_id: string
  score: number
  level: 'weak' | 'building' | 'familiar' | 'mastered'
  attempts: number
  correct_count: number
  wrong_count: number
  streak: number
  last_result: '' | 'correct' | 'wrong'
  last_answered_at: string
  next_review_at: string
  review_interval_days: number
  updated_at: string
}

export interface MistakeRecord {
  id: string
  point_id: string
  question: string
  user_answer: string
  expected_answer: string
  source_ref: Record<string, string>
  status: 'open' | 'resolved'
  review_count: number
  created_at: string
  updated_at: string
  resolved_at: string
}

export interface MasteryState {
  schema_version: number
  knowledge_points: KnowledgePoint[]
  mastery: Record<string, MasteryRecord>
  mistakes: MistakeRecord[]
  created_at: string
  updated_at: string
}

export interface MasteryKnowledgePointInput {
  id?: string
  point_id?: string
  title: string
  aliases?: string[]
  source_refs?: Array<Record<string, string>>
}

export interface MasteryAnswerResultInput {
  point_id: string
  correct: boolean
  question?: string
  user_answer?: string
  expected_answer?: string
  difficulty?: 'easy' | 'normal' | 'hard' | string
  confidence?: number
  source_ref?: Record<string, string>
}

export interface MasteryUpdateRequest {
  knowledge_point?: MasteryKnowledgePointInput
  answer_result?: MasteryAnswerResultInput
}

export interface MasteryDashboardItem {
  id: string
  type: 'weak_point' | 'mastery_review'
  title: string
  score: number
  level: MasteryRecord['level'] | string
  attempts: number
  wrong_count: number
  next_review_at: string
}

export interface DashboardMastery {
  knowledge_point_count: number
  tracked_count: number
  average_score: number
  weak_count: number
  building_count: number
  familiar_count: number
  mastered_count: number
  due_review_count: number
  open_mistake_count: number
  weakest_points: MasteryDashboardItem[]
  due_reviews: MasteryDashboardItem[]
}

export interface DashboardLearningProgress {
  total: number
  done: number
  doing: number
  todo: number
  progress_percent: number
  remaining_minutes: number
  completed_minutes: number
  next_item_id: number | null
  next_item_title: string
}

export interface DashboardMaterials {
  file_count: number
  generated_file_count: number
  total_bytes: number
  by_extension: Record<string, number>
  indexed_files: number
  indexed_chunks: number
  schema_version: number | null
  tokenizer_version: string
}

export interface DashboardReviewItem {
  id: number
  title: string
  kind: StudyPlanItem['kind'] | string
  status: StudyPlanItem['status'] | string
  estimated_minutes: number
  source_file_name: string
}

export interface DashboardActivity {
  type: string
  title: string
  created_at: string
}

export interface DashboardGeneratedArtifacts {
  total: number
  summaries: number
  quizzes: number
  other: number
  latest: DashboardActivity | null
}

export interface CourseDashboard {
  course: {
    id: string
    name: string
    path: string
  }
  learning_progress: DashboardLearningProgress
  recent_activity: DashboardActivity[]
  materials: DashboardMaterials
  review_queue: DashboardReviewItem[]
  mastery?: DashboardMastery
  generated_artifacts: DashboardGeneratedArtifacts
}

export interface ConfigResponse {
  root_folder: string
  ai_provider: string
  ai_configured: boolean
  mineru_auto: boolean
  mineru_configured: boolean
  web_search_configured?: boolean
}

export interface ConfigCapabilityStatus {
  key: string
  label: string
  status: 'ok' | 'warning' | 'error' | 'skip'
  enabled: boolean
  detail: string
  missing: string[]
  provider?: string
  auto?: boolean
  index_files?: number
  total_chunks?: number
  schema_versions?: number[]
  model?: string
  dimensions?: number
  backup_file_count?: number
  mode?: string
}

export interface ConfigStatusResponse {
  data_dir: string
  root_folder: string
  overall: 'ok' | 'warning' | 'error'
  capabilities: ConfigCapabilityStatus[]
}

export interface CoursesResponse {
  courses: Course[]
}

export interface MessagesResponse {
  messages: Message[]
}

export interface NotesResponse {
  notes: Note[]
}

export interface StudyPlanResponse {
  plan: StudyPlan
}

export interface CourseDashboardResponse {
  dashboard: CourseDashboard
}

export interface MasteryResponse {
  mastery: MasteryState
}

export interface SaveMasteryResponse {
  ok: boolean
  mastery: MasteryState
}

export interface SaveStudyPlanResponse {
  ok: boolean
  plan: StudyPlan
}

export interface MemoryResponse {
  memory: string
}

export interface StudyContentResponse {
  content: string
  citations: Citation[]
  llm_status?: 'used' | 'fallback' | 'disabled' | 'skipped'
}

export interface SaveConfigResponse {
  ok: boolean
  config: {
    root_folder: string
  }
}

export interface SaveNotesResponse {
  ok: boolean
  notes: Note[]
}

export interface ClearCourseMemoryResponse {
  ok: boolean
  messages: Message[]
  memory: string
}

export interface IndexResult {
  ok: boolean
  indexed_files: number
  total_chunks: number
}

export interface IndexJob {
  id: string
  course_id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  result: IndexResult | null
  error: string
  started_at: string | null
  updated_at: string
  finished_at: string | null
  progress: number
  current_file: IndexJobFile | null
  processed_files: number
  total_files: number
  error_files: IndexJobErrorFile[]
}

export interface IndexJobFile {
  file_id: string | null
  file_name: string
  path: string
}

export interface IndexJobErrorFile extends IndexJobFile {
  error: string
}

export interface ArtifactResult {
  ok: boolean
  content: string
  citations: Citation[]
  llm_status?: 'used' | 'fallback' | 'disabled' | 'skipped'
  summary_method?: 'map_reduce' | 'single_prompt' | 'extractive'
  artifact: {
    name: string
    path: string
  }
  courses: Course[]
}

export interface ChatResult {
  answer: string
  citations: Citation[]
  memory: string
  mode: string
  trace: TraceStep[]
  retrieval_trace?: {
    selected: Array<{
      file_name: string
      section_title: string
      material_type: string
      score: number
      query_coverage: number
      matched_terms: string[]
      retrieval_method: string
    }>
  }
  citation_check?: {
    supported: boolean
    unsupported_claims: Array<{
      sentence: string
      reason: string
    }>
    stats: {
      claim_count: number
      assertive_claim_count: number
      unsupported_count: number
      uncited_count: number
    }
  }
  unsupported_claims?: Array<{
    sentence: string
    reason: string
  }>
  llm_status?: 'used' | 'fallback' | 'disabled'
  web_search_status?: 'used' | 'empty' | 'failed' | 'disabled' | 'skipped'
}

export type ChatStreamEvent =
  | { type: 'status'; stage: string; detail: string }
  | { type: 'delta'; delta: string }
  | { type: 'done'; result: ChatResult }
  | { type: 'error'; error: string }

export interface UploadResult {
  ok: boolean
  saved: Array<{
    name: string
    path: string
  }>
  courses: Course[]
}
