'use client';

import { useEffect, useState } from 'react';
import { supabase, TaskResult } from '@/lib/supabase';
import StatsCard from '@/components/StatsCard';
import ResultCard from '@/components/ResultCard';
import { Activity, CheckCircle, Clock, TrendingUp } from 'lucide-react';

export default function Dashboard() {
  const [results, setResults] = useState<TaskResult[]>([]);
  const [stats, setStats] = useState({
    total: 0,
    passRate: 0,
    avgScore: 0,
    todayCount: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
    
    // Realtime subscription
    if (!supabase) return;
    
    const subscription = supabase
      .channel('task_results')
      .on('postgres_changes', { 
        event: 'INSERT', 
        schema: 'public', 
        table: 'task_results' 
      }, (payload) => {
        setResults(prev => [payload.new as TaskResult, ...prev].slice(0, 10));
      })
      .subscribe();

    return () => {
      subscription.unsubscribe();
    };
  }, []);

  async function fetchData() {
    setLoading(true);
    
    if (!supabase) {
      setLoading(false);
      return;
    }
    
    // Fetch recent results
    const { data: resultsData } = await supabase
      .from('task_results')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(10);

    // Fetch stats
    const { data: allResults } = await supabase
      .from('task_results')
      .select('score, passed, created_at');

    if (resultsData) setResults(resultsData);
    
    if (allResults && allResults.length > 0) {
      const today = new Date().toISOString().split('T')[0];
      const todayResults = allResults.filter(r => r.created_at.startsWith(today));
      const passedCount = allResults.filter(r => r.passed).length;
      const avgScore = allResults.reduce((sum, r) => sum + r.score, 0) / allResults.length;
      
      setStats({
        total: allResults.length,
        passRate: Math.round((passedCount / allResults.length) * 100),
        avgScore: Math.round(avgScore * 10) / 10,
        todayCount: todayResults.length,
      });
    }
    
    setLoading(false);
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 mt-1">Overview of your image editing pipeline</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <StatsCard 
          title="Today's Tasks" 
          value={stats.todayCount}
          icon={<Activity size={20} />}
        />
        <StatsCard 
          title="Pass Rate" 
          value={`${stats.passRate}%`}
          subtitle={stats.passRate >= 80 ? '↑ Good' : '↓ Needs attention'}
          trend={stats.passRate >= 80 ? 'up' : 'down'}
          icon={<CheckCircle size={20} />}
        />
        <StatsCard 
          title="Avg Score" 
          value={stats.avgScore}
          icon={<TrendingUp size={20} />}
        />
        <StatsCard 
          title="Total Tasks" 
          value={stats.total}
          icon={<Clock size={20} />}
        />
      </div>

      {/* Recent Results */}
      <div>
        <h2 className="text-xl font-bold text-gray-900 mb-4">Recent Results</h2>
        <div className="space-y-3">
          {results.length === 0 ? (
            <div className="text-center py-12 text-gray-500 bg-white rounded-xl border">
              No results yet. Tasks will appear here when processed.
            </div>
          ) : (
            results.map((result) => (
              <ResultCard key={result.id} result={result} />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
