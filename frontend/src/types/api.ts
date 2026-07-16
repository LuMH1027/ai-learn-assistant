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
  file_id: string
  file_name: string
  quote: string
  page: number | null
  chunk_index: number
  score: number
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
}

export interface Note {
  id: number
  title: string
  content: string
  created_at: string
}

export interface ConfigResponse {
  root_folder: string
  ai_provider: string
  ai_configured: boolean
  mineru_auto: boolean
  mineru_configured: boolean
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

export interface MemoryResponse {
  memory: string
}

export interface StudyContentResponse {
  content: string
  citations: Citation[]
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

export interface IndexResult {
  ok: boolean
  indexed_files: number
  total_chunks: number
}

export interface ArtifactResult {
  ok: boolean
  content: string
  citations: Citation[]
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
  llm_status?: 'used' | 'fallback' | 'disabled'
}

export interface UploadResult {
  ok: boolean
  saved: Array<{
    name: string
    path: string
  }>
  courses: Course[]
}
