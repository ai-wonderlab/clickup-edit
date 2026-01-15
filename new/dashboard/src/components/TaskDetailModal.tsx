'use client';

import { useState, useEffect } from 'react';
import { supabase, TaskResult, TaskLog } from '@/lib/supabase';
import { 
  X, Clock, CheckCircle, XCircle, ChevronDown, ChevronRight,
  Sparkles, Image, Eye, RotateCcw, AlertTriangle, ThumbsUp, ThumbsDown,
  Copy, Check, MessageSquare
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

// Sub-component for enhanced prompts
function EnhancedPromptDisplay({ llmResponses }: { llmResponses: any[] }) {
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);

  const handleCopy = async (text: string, idx: number) => {
    await navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  if (!llmResponses || llmResponses.length === 0) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-purple-700">
        <MessageSquare className="w-4 h-4" />
        <span className="text-sm font-semibold">🤖 LLM Enhanced Prompts</span>
      </div>
      {llmResponses.map((resp: any, idx: number) => (
        <div key={idx} className="border border-purple-200 rounded-lg overflow-hidden">
          <div className="flex items-center justify-between px-3 py-2 bg-purple-50">
            <span className="text-xs font-medium text-purple-700">
              Model: {resp.model}
            </span>
            <button
              onClick={() => handleCopy(resp.enhanced_prompt, idx)}
              className="flex items-center gap-1 text-xs text-purple-600 hover:text-purple-800"
            >
              {copiedIdx === idx ? (
                <><Check className="w-3 h-3" /> Copied</>
              ) : (
                <><Copy className="w-3 h-3" /> Copy</>
              )}
            </button>
          </div>
          <pre className="p-3 text-xs font-mono whitespace-pre-wrap bg-white max-h-64 overflow-y-auto">
            {resp.enhanced_prompt}
          </pre>
        </div>
      ))}
    </div>
  );
}

// Sub-component for validation results
function ValidationResultsDisplay({ validationResults }: { validationResults: any[] }) {
  if (!validationResults || validationResults.length === 0) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-green-700">
        <Eye className="w-4 h-4" />
        <span className="text-sm font-semibold">🔍 Validation Results</span>
      </div>
      {validationResults.map((v: any, idx: number) => (
        <div 
          key={idx} 
          className={`border rounded-lg overflow-hidden ${
            v.passed ? 'border-green-200' : 'border-red-200'
          }`}
        >
          <div className={`flex items-center justify-between px-3 py-2 ${
            v.passed ? 'bg-green-50' : 'bg-red-50'
          }`}>
            <div className="flex items-center gap-3">
              <span className="text-xs font-medium text-gray-700">
                {v.model}
              </span>
              <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                v.passed 
                  ? 'bg-green-200 text-green-800' 
                  : 'bg-red-200 text-red-800'
              }`}>
                {v.passed ? '✓ PASS' : '✗ FAIL'}
              </span>
              <span className="text-lg font-bold">
                {v.score}/10
              </span>
            </div>
          </div>
          
          {/* Issues */}
          {v.issues && v.issues.length > 0 && (
            <div className="px-3 py-2 border-t border-gray-100">
              <p className="text-xs font-semibold text-red-600 mb-1">Issues:</p>
              <ul className="list-disc list-inside text-xs text-red-500 space-y-0.5">
                {v.issues.map((issue: string, i: number) => (
                  <li key={i}>{issue}</li>
                ))}
              </ul>
            </div>
          )}
          
          {/* Reasoning */}
          {v.reasoning && (
            <div className="px-3 py-2 border-t border-gray-100 bg-gray-50">
              <p className="text-xs font-semibold text-gray-600 mb-1">Full Reasoning:</p>
              <pre className="text-xs font-mono whitespace-pre-wrap text-gray-600 max-h-48 overflow-y-auto">
                {v.reasoning}
              </pre>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

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
        return data;
      }
      return JSON.stringify(data, null, 2);
    } catch {
      return String(data);
    }
  };

  // Render expanded content based on phase type
  const renderExpandedContent = (log: TaskLog) => {
    const output = log.output as any;
    const input = log.input as any;

    return (
      <div className="p-4 border-t border-gray-200 space-y-4">
        {/* Error */}
        {log.error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-sm font-medium text-red-700 mb-1">Error</p>
            <p className="text-sm text-red-600 font-mono">{log.error}</p>
          </div>
        )}

        {/* Enhanced Prompts (for enhancement phase) */}
        {log.phase === 'enhancement' && output?.llm_responses && (
          <EnhancedPromptDisplay llmResponses={output.llm_responses} />
        )}

        {/* Validation Results (for validation phase) */}
        {log.phase === 'validation' && output?.validation_results && (
          <ValidationResultsDisplay validationResults={output.validation_results} />
        )}

        {/* Original Prompt (for enhancement phase) */}
        {log.phase === 'enhancement' && input?.original_prompt && (
          <div>
            <p className="text-sm font-medium text-gray-700 mb-2">📝 Original Prompt</p>
            <pre className="p-3 bg-gray-50 border border-gray-200 rounded-lg text-xs font-mono whitespace-pre-wrap max-h-32 overflow-y-auto">
              {input.original_prompt}
            </pre>
          </div>
        )}

        {/* Generic Input (for other phases) */}
        {log.input && log.phase !== 'enhancement' && (
          <div>
            <p className="text-sm font-medium text-gray-700 mb-2">Input</p>
            <pre className="p-3 bg-gray-50 border border-gray-200 rounded-lg text-xs font-mono overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap">
              {formatJson(log.input)}
            </pre>
          </div>
        )}

        {/* Generic Output (for phases without special handling) */}
        {log.output && log.phase !== 'enhancement' && log.phase !== 'validation' && (
          <div>
            <p className="text-sm font-medium text-gray-700 mb-2">Output</p>
            <pre className="p-3 bg-gray-50 border border-gray-200 rounded-lg text-xs font-mono overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap">
              {formatJson(log.output)}
            </pre>
          </div>
        )}

        {/* Summary stats for enhancement */}
        {log.phase === 'enhancement' && output && (
          <div className="flex items-center gap-4 text-xs text-gray-500 pt-2 border-t">
            <span>Enhanced: {output.enhanced_count} prompts</span>
            {input?.image_count > 0 && <span>Images: {input.image_count}</span>}
            {input?.has_previous_feedback && <span className="text-yellow-600">Has feedback from previous iteration</span>}
          </div>
        )}

        {/* Summary stats for validation */}
        {log.phase === 'validation' && output && (
          <div className="flex items-center gap-4 text-xs text-gray-500 pt-2 border-t">
            <span>Best Score: {output.best_score}/10</span>
            <span>Passed: {output.passed_count}</span>
          </div>
        )}

        {/* Summary stats for generation */}
        {log.phase === 'generation' && output && (
          <div className="flex items-center gap-4 text-xs text-gray-500">
            <span>Generated: {output.generated_count} images</span>
            {output.aspect_ratio && <span>Aspect: {output.aspect_ratio}</span>}
            {output.models_used && <span>Models: {output.models_used.join(', ')}</span>}
          </div>
        )}
      </div>
    );
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
                        {isExpanded && renderExpandedContent(log)}
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
