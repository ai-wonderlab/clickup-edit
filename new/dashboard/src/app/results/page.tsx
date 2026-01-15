'use client';

import { useEffect, useState } from 'react';
import { supabase, TaskResult } from '@/lib/supabase';
import ResultCard from '@/components/ResultCard';
import TaskDetailModal from '@/components/TaskDetailModal';
import { RotateCcw } from 'lucide-react';
import Toast, { useToast } from '@/components/Toast';

export default function Results() {
  const [results, setResults] = useState<TaskResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'passed' | 'failed'>('all');
  const [selectedResult, setSelectedResult] = useState<TaskResult | null>(null);
  const { toasts, addToast, removeToast } = useToast();

  useEffect(() => {
    console.log('[Results] Component mounted');
    fetchResults();
  }, []);

  const fetchResults = async () => {
    console.log('[Results] Fetching results...');
    
    if (!supabase) {
      console.warn('[Results] Supabase not configured');
      addToast('error', 'Supabase not configured');
      setLoading(false);
      return;
    }

    try {
      const { data, error } = await supabase
        .from('task_results')
        .select('*')
        .order('created_at', { ascending: false })
        .limit(50);

      if (error) {
        console.error('[Results] Error:', error);
        throw error;
      }

      console.log('[Results] Fetched:', data?.length || 0);
      setResults(data || []);
      addToast('info', `Loaded ${data?.length || 0} results`);
    } catch (err) {
      console.error('[Results] Error:', err);
      addToast('error', 'Failed to load results');
    } finally {
      setLoading(false);
    }
  };

  const filteredResults = results.filter((r) => {
    if (filter === 'passed') return r.passed;
    if (filter === 'failed') return !r.passed;
    return true;
  });

  const handleResultClick = (result: TaskResult) => {
    console.log('[Results] Clicked result:', result.task_id);
    setSelectedResult(result);
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
          <h1 className="text-2xl font-bold text-gray-900">Results</h1>
          <p className="text-gray-600 mt-1">Click on a result to view full processing history</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={filter}
            onChange={(e) => {
              console.log('[Results] Filter changed:', e.target.value);
              setFilter(e.target.value as any);
            }}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
          >
            <option value="all">All Results</option>
            <option value="passed">Passed Only</option>
            <option value="failed">Failed Only</option>
          </select>
          <button
            onClick={fetchResults}
            className="flex items-center gap-2 px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <RotateCcw className="w-4 h-4" />
            Refresh
          </button>
        </div>
      </div>

      {filteredResults.length === 0 ? (
        <div className="bg-white border border-gray-200 rounded-lg p-8 text-center text-gray-500">
          No results found. Tasks will appear here when processed.
        </div>
      ) : (
        <div className="space-y-3">
          {filteredResults.map((result) => (
            <ResultCard 
              key={result.id} 
              result={result} 
              onClick={() => handleResultClick(result)}
            />
          ))}
        </div>
      )}

      {/* Task Detail Modal */}
      {selectedResult && (
        <TaskDetailModal
          result={selectedResult}
          onClose={() => {
            console.log('[Results] Closing detail modal');
            setSelectedResult(null);
          }}
        />
      )}

      <Toast toasts={toasts} removeToast={removeToast} />
    </div>
  );
}
