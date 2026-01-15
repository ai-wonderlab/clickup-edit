'use client';

import { useEffect, useState } from 'react';
import { supabase, PromptHistory } from '@/lib/supabase';
import { History, RotateCcw } from 'lucide-react';

export default function HistoryPage() {
  const [history, setHistory] = useState<PromptHistory[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchHistory();
  }, []);

  async function fetchHistory() {
    if (!supabase) {
      setLoading(false);
      return;
    }
    
    const { data } = await supabase
      .from('prompt_history')
      .select('*')
      .order('changed_at', { ascending: false })
      .limit(50);

    if (data) setHistory(data);
    setLoading(false);
  }

  async function restoreVersion(promptId: string, content: string) {
    if (!confirm(`Restore ${promptId} to this version?`) || !supabase) return;
    
    await supabase
      .from('prompts')
      .update({ content, updated_at: new Date().toISOString() })
      .eq('prompt_id', promptId);
    
    alert('Restored successfully!');
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Prompt History</h1>
        <p className="text-gray-500 mt-1">View and restore previous prompt versions</p>
      </div>

      {loading ? (
        <div className="text-center py-8">Loading...</div>
      ) : history.length === 0 ? (
        <div className="text-center py-12 text-gray-500 bg-white rounded-xl border">
          No history yet. Changes will appear here when prompts are edited.
        </div>
      ) : (
        <div className="space-y-4">
          {history.map((item) => (
            <div
              key={item.id}
              className="p-4 bg-white rounded-lg border hover:shadow-md transition-all"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-3">
                  <History className="text-gray-400" size={20} />
                  <span className="font-mono text-blue-600 font-bold">
                    {item.prompt_id}
                  </span>
                  <span className="text-sm text-gray-500">
                    Version {item.version}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm text-gray-400">
                    {new Date(item.changed_at).toLocaleString()}
                  </span>
                  <button
                    onClick={() => restoreVersion(item.prompt_id, item.content)}
                    className="flex items-center gap-1 px-3 py-1 text-sm text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                  >
                    <RotateCcw size={14} />
                    Restore
                  </button>
                </div>
              </div>
              <div className="text-sm text-gray-600 bg-gray-50 p-3 rounded font-mono truncate">
                {item.content.slice(0, 200)}...
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

