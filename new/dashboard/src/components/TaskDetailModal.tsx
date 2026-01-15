'use client';

import { useState, useEffect } from 'react';
import { supabase, TaskResult, TaskLog } from '@/lib/supabase';
import { 
  X, Clock, CheckCircle, XCircle, ChevronDown, ChevronRight,
  Sparkles, Image, Eye, RotateCcw, AlertTriangle, ThumbsUp, ThumbsDown
} from 'lucide-react';

interface TaskDetailModalProps {
  result: TaskResult;
  onClose: () => void;
}

const PHASE_ICONS: Record<string, any> = {
  enhancement: Sparkles,
  generation: Image,
  validation: Eye,
  iteration: RotateCcw,
  fallback: AlertTriangle,
  parsing: Clock,
  start: Clock,
  end: CheckCircle,
};

const PHASE_COLORS: Record<string, string> = {
  enhancement: 'bg-purple-100 text-purple-700 border-purple-200',
  generation: 'bg-blue-100 text-blue-700 border-blue-200',
  validation: 'bg-green-100 text-green-700 border-green-200',
  iteration: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  fallback: 'bg-red-100 text-red-700 border-red-200',
  parsing: 'bg-gray-100 text-gray-700 border-gray-200',
  start: 'bg-indigo-100 text-indigo-700 border-indigo-200',
  end: 'bg-emerald-100 text-emerald-700 border-emerald-200',
};

export default function TaskDetailModal({ result, onClose }: TaskDetailModalProps) {
  const [logs, setLogs] = useState<TaskLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedLogs, setExpandedLogs] = useState<Set<string>>(new Set());

  useEffect(() => {
    console.log('[TaskDetail] Opening for task:', result.task_id);
    fetchLogs();
    
    // Close on Escape
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [result.task_id, onClose]);

  const fetchLogs = async () => {
    if (!supabase) {
      console.warn('[TaskDetail] Supabase not configured');
      setLoading(false);
      return;
    }

    try {
      console.log('[TaskDetail] Fetching logs for:', result.task_id);
      const { data, error } = await supabase
        .from('task_logs')
        .select('*')
        .eq('task_id', result.task_id)
        .order('created_at', { ascending: true });

      if (error) throw error;
      
      console.log('[TaskDetail] Fetched logs:', data?.length || 0);
      setLogs(data || []);
    } catch (err) {
      console.error('[TaskDetail] Error:', err);
    } finally {
      setLoading(false);
    }
  };

  const toggleLog = (logId: string) => {
    setExpandedLogs(prev => {
      const next = new Set(prev);
      if (next.has(logId)) {
        next.delete(logId);
      } else {
        next.add(logId);
      }
      return next;
    });
  };

  const formatDuration = (ms: number | null) => {
    if (!ms) return '-';
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  const formatTimestamp = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const formatJson = (data: any) => {
    if (!data) return 'null';
    try {
      if (typeof data === 'string') {
        // Truncate long strings
        if (data.length > 500) {
          return data.substring(0, 500) + '...';
        }
        return data;
      }
      return JSON.stringify(data, null, 2);
    } catch {
      return String(data);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 mb-1">
              {result.passed ? (
                <CheckCircle className="w-5 h-5 text-green-500 flex-shrink-0" />
              ) : (
                <XCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
              )}
              <h2 className="font-semibold text-gray-900 truncate">
                {result.request}
              </h2>
            </div>
            <div className="flex items-center gap-4 text-sm text-gray-500">
              <span>Score: {result.score}/10</span>
              <span>•</span>
              <span>{result.model_used}</span>
              <span>•</span>
              <span>{result.iterations} iteration{result.iterations !== 1 ? 's' : ''}</span>
              {result.user_feedback && (
                <>
                  <span>•</span>
                  <span className={`flex items-center gap-1 ${
                    result.user_feedback === 'Like' ? 'text-green-600' : 'text-red-600'
                  }`}>
                    {result.user_feedback === 'Like' ? (
                      <ThumbsUp className="w-4 h-4" />
                    ) : (
                      <ThumbsDown className="w-4 h-4" />
                    )}
                    {result.user_feedback}
                  </span>
                </>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors ml-4"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            </div>
          ) : logs.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <Clock className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>No processing logs found for this task</p>
              <p className="text-sm mt-1">Logs may not have been recorded for older tasks</p>
            </div>
          ) : (
            <div className="space-y-3">
              {/* Timeline */}
              <div className="relative">
                {logs.map((log, index) => {
                  const Icon = PHASE_ICONS[log.phase] || Clock;
                  const colorClass = PHASE_COLORS[log.phase] || 'bg-gray-100 text-gray-700 border-gray-200';
                  const isExpanded = expandedLogs.has(log.id);
                  const isLast = index === logs.length - 1;

                  return (
                    <div key={log.id} className="relative pl-8">
                      {/* Timeline line */}
                      {!isLast && (
                        <div className="absolute left-[15px] top-8 bottom-0 w-0.5 bg-gray-200" />
                      )}
                      
                      {/* Timeline dot */}
                      <div className={`absolute left-0 top-1 w-8 h-8 rounded-full flex items-center justify-center border-2 ${
                        log.success ? 'bg-green-100 border-green-300' : 'bg-red-100 border-red-300'
                      }`}>
                        <Icon className={`w-4 h-4 ${log.success ? 'text-green-600' : 'text-red-600'}`} />
                      </div>

                      {/* Log card */}
                      <div 
                        className={`mb-4 border rounded-lg overflow-hidden cursor-pointer transition-all ${
                          isExpanded ? 'ring-2 ring-blue-300' : 'hover:border-gray-300'
                        }`}
                        onClick={() => toggleLog(log.id)}
                      >
                        {/* Log header */}
                        <div className="flex items-center justify-between p-3 bg-gray-50">
                          <div className="flex items-center gap-3">
                            <span className={`px-2 py-1 rounded text-xs font-medium border ${colorClass}`}>
                              {log.phase.toUpperCase()}
                            </span>
                            {log.iteration && (
                              <span className="text-xs text-gray-500">
                                Iteration {log.iteration}
                              </span>
                            )}
                            {log.model_used && (
                              <span className="text-xs text-gray-400">
                                {log.model_used}
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-3">
                            <span className="text-xs text-gray-400">
                              {formatTimestamp(log.created_at)}
                            </span>
                            <span className="text-xs text-gray-400">
                              {formatDuration(log.duration_ms)}
                            </span>
                            {log.success ? (
                              <CheckCircle className="w-4 h-4 text-green-500" />
                            ) : (
                              <XCircle className="w-4 h-4 text-red-500" />
                            )}
                            {isExpanded ? (
                              <ChevronDown className="w-4 h-4 text-gray-400" />
                            ) : (
                              <ChevronRight className="w-4 h-4 text-gray-400" />
                            )}
                          </div>
                        </div>

                        {/* Expanded content */}
                        {isExpanded && (
                          <div className="p-4 border-t border-gray-200 space-y-4">
                            {/* Error */}
                            {log.error && (
                              <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                                <p className="text-sm font-medium text-red-700 mb-1">Error</p>
                                <p className="text-sm text-red-600 font-mono">{log.error}</p>
                              </div>
                            )}

                            {/* Input */}
                            {log.input && (
                              <div>
                                <p className="text-sm font-medium text-gray-700 mb-2">Input</p>
                                <pre className="p-3 bg-gray-50 border border-gray-200 rounded-lg text-xs font-mono overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap">
                                  {formatJson(log.input)}
                                </pre>
                              </div>
                            )}

                            {/* Output */}
                            {log.output && (
                              <div>
                                <p className="text-sm font-medium text-gray-700 mb-2">Output</p>
                                <pre className="p-3 bg-gray-50 border border-gray-200 rounded-lg text-xs font-mono overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap">
                                  {formatJson(log.output)}
                                </pre>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-200 bg-gray-50">
          <div className="flex items-center justify-between text-sm text-gray-500">
            <span>Task ID: {result.task_id}</span>
            <span>ClickUp: {result.clickup_task_id}</span>
            <span>{new Date(result.created_at).toLocaleString()}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

