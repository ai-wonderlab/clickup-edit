'use client';

import { useEffect, useState } from 'react';
import { supabase, TaskResult, TaskLog } from '@/lib/supabase';
import ResultCard from '@/components/ResultCard';

export default function Results() {
  const [results, setResults] = useState<TaskResult[]>([]);
  const [selectedTask, setSelectedTask] = useState<string | null>(null);
  const [logs, setLogs] = useState<TaskLog[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchResults();
  }, []);

  async function fetchResults() {
    if (!supabase) {
      setLoading(false);
      return;
    }
    
    const { data } = await supabase
      .from('task_results')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(50);

    if (data) setResults(data);
    setLoading(false);
  }

  async function fetchLogs(taskId: string) {
    if (!supabase) return;
    
    const { data } = await supabase
      .from('task_logs')
      .select('*')
      .eq('task_id', taskId)
      .order('created_at', { ascending: true });

    if (data) setLogs(data);
    setSelectedTask(taskId);
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Results</h1>
        <p className="text-gray-500 mt-1">View all task results and debug info</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Results List */}
        <div>
          <h2 className="text-xl font-bold text-gray-900 mb-4">Recent Tasks</h2>
          <div className="space-y-3 max-h-[70vh] overflow-y-auto">
            {loading ? (
              <div className="text-center py-8">Loading...</div>
            ) : results.length === 0 ? (
              <div className="text-center py-12 text-gray-500">No results yet</div>
            ) : (
              results.map((result) => (
                <ResultCard
                  key={result.id}
                  result={result}
                  onClick={() => fetchLogs(result.task_id)}
                />
              ))
            )}
          </div>
        </div>

        {/* Debug Panel */}
        <div>
          <h2 className="text-xl font-bold text-gray-900 mb-4">Pipeline Trace</h2>
          {selectedTask ? (
            <div className="bg-white rounded-xl border p-6 space-y-4">
              <h3 className="font-mono text-sm text-gray-500">
                Task: {selectedTask}
              </h3>
              {logs.map((log, index) => (
                <div
                  key={log.id}
                  className={`p-4 rounded-lg border-l-4 ${
                    log.success
                      ? 'border-green-500 bg-green-50'
                      : 'border-red-500 bg-red-50'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-bold text-gray-900">
                      {index + 1}. {log.phase.toUpperCase()}
                    </span>
                    <span className="text-sm text-gray-500">
                      {log.duration_ms}ms
                    </span>
                  </div>
                  {log.model_used && (
                    <div className="text-sm text-gray-600">
                      Model: {log.model_used}
                    </div>
                  )}
                  {log.error && (
                    <div className="text-sm text-red-600 mt-2">
                      Error: {log.error}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="bg-white rounded-xl border p-12 text-center text-gray-500">
              Click a task to see pipeline trace
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

