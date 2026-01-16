import { createClient, SupabaseClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || '';
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '';

// Create client only if credentials are provided
let supabase: SupabaseClient | null = null;

if (supabaseUrl && supabaseAnonKey) {
  supabase = createClient(supabaseUrl, supabaseAnonKey);
  console.log('[Supabase] Client initialized');
} else {
  console.warn('[Supabase] Missing credentials - URL:', !!supabaseUrl, 'Key:', !!supabaseAnonKey);
}

export { supabase };

// Types
export interface Prompt {
  id: string;
  prompt_id: string;
  name: string;
  category: string;
  content: string;
  updated_at: string;
}

export interface Parameter {
  id: string;
  key: string;
  value: string;
  type: string;
  min_value: number | null;
  max_value: number | null;
  updated_at: string;
}

export interface TaskResult {
  id: string;
  task_id: string;
  run_id: string | null;  // Unique identifier for this pipeline run
  clickup_task_id: string;
  task_name: string | null;  // ClickUp task name for display
  request: string;
  score: number;
  passed: boolean;
  model_used: string;
  iterations: number;
  user_feedback: string | null;
  user_notes: string | null;
  created_at: string;
}

export interface TaskLog {
  id: string;
  task_id: string;
  run_id: string | null;  // Unique identifier for this pipeline run
  phase: string;
  model_used: string | null;
  iteration: number | null;
  input: any;
  output: any;
  duration_ms: number | null;
  success: boolean;
  error: string | null;
  created_at: string;
}

export interface PromptHistory {
  id: string;
  prompt_id: string;
  version: number;
  content: string;
  changed_at: string;
}
