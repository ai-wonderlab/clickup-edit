'use client';

import { useEffect, useState } from 'react';
import { supabase, PromptHistory } from '@/lib/supabase';
import { History, RotateCcw, Copy, Check, ChevronDown, ChevronUp } from 'lucide-react';
import Toast, { useToast } from '@/components/Toast';

interface ExpandedState {
  [key: string]: boolean;
}

export default function HistoryPage() {
  const [history, setHistory] = useState<PromptHistory[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<ExpandedState>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const { toasts, addToast, removeToast } = useToast();

  useEffect(() => {
    fetchHistory();
  }, []);

  const fetchHistory = async () => {
    if (!supabase) {
      addToast('error', 'Supabase not configured');
      setLoading(false);
      return;
    }

    try {
      const { data, error } = await supabase
        .from('prompt_history')
        .select('*')
        .order('changed_at', { ascending: false })
        .limit(50);

      if (error) throw error;
      setHistory(data || []);
      addToast('info', `Loaded ${data?.length || 0} history entries`);
    } catch (err) {
      addToast('error', 'Failed to load history');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const toggleExpanded = (id: string) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const handleCopy = async (content: string, id: string) => {
    await navigator.clipboard.writeText(content);
    setCopiedId(id);
    addToast('success', 'Copied to clipboard');
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleRestore = async (entry: PromptHistory) => {
    if (!supabase) return;

    try {
      const { error } = await supabase
        .from('prompts')
        .update({
          content: entry.content,
          updated_at: new Date().toISOString(),
        })
        .eq('prompt_id', entry.prompt_id);

      if (error) throw error;
      addToast('success', `Restored ${entry.prompt_id} to version ${entry.version}`);
    } catch (err) {
      addToast('error', 'Failed to restore prompt');
      console.error(err);
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Prompt History</h1>
          <p className="text-gray-600 mt-1">View and restore previous prompt versions</p>
        </div>
        <button
          onClick={fetchHistory}
          className="flex items-center gap-2 px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <RotateCcw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {history.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <History className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>No history entries found</p>
        </div>
      ) : (
        <div className="space-y-3">
          {history.map((entry) => (
            <div
              key={entry.id}
              className="border border-gray-200 rounded-lg overflow-hidden bg-white"
            >
              {/* Header */}
              <div
                onClick={() => toggleExpanded(entry.id)}
                className="flex items-center justify-between p-4 cursor-pointer hover:bg-gray-50 transition-colors"
              >
                <div className="flex items-center gap-4 min-w-0 flex-1">
                  <History className="w-5 h-5 text-gray-400 flex-shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono font-semibold text-blue-600">
                        {entry.prompt_id}
                      </span>
                      <span className="px-2 py-0.5 bg-gray-100 rounded text-xs text-gray-500">
                        Version {entry.version}
                      </span>
                    </div>
                    <p className="text-sm text-gray-500 truncate mt-1 max-w-full">
                      {entry.content.substring(0, 100)}...
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0 ml-4">
                  <span className="text-xs text-gray-400 hidden sm:block">
                    {formatDate(entry.changed_at)}
                  </span>
                  {expanded[entry.id] ? (
                    <ChevronUp className="w-5 h-5 text-gray-400" />
                  ) : (
                    <ChevronDown className="w-5 h-5 text-gray-400" />
                  )}
                </div>
              </div>

              {/* Expanded Content */}
              {expanded[entry.id] && (
                <div className="border-t border-gray-200 p-4 bg-gray-50">
                  <div className="mb-3 text-xs text-gray-500 sm:hidden">
                    {formatDate(entry.changed_at)}
                  </div>
                  <pre className="p-4 bg-white border border-gray-200 rounded-lg text-sm font-mono whitespace-pre-wrap break-words overflow-x-auto max-h-64 overflow-y-auto">
                    {entry.content}
                  </pre>
                  <div className="flex items-center gap-2 mt-3">
                    <button
                      onClick={() => handleCopy(entry.content, entry.id)}
                      className="flex items-center gap-2 px-3 py-2 text-gray-600 hover:bg-gray-200 rounded-lg transition-colors"
                    >
                      {copiedId === entry.id ? (
                        <>
                          <Check className="w-4 h-4 text-green-500" />
                          <span className="text-green-600">Copied</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-4 h-4" />
                          Copy
                        </>
                      )}
                    </button>
                    <button
                      onClick={() => handleRestore(entry)}
                      className="flex items-center gap-2 px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                    >
                      <RotateCcw className="w-4 h-4" />
                      Restore
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <Toast toasts={toasts} removeToast={removeToast} />
    </div>
  );
}