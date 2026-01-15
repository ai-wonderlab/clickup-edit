export interface Stats {
  totalTasks: number;
  passRate: number;
  avgScore: number;
  avgDuration: number;
}

export interface PipelinePhase {
  id: string;
  name: string;
  icon: string;
  prompts: string[];
  description: string;
}

