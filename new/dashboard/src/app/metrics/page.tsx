'use client';

import { useEffect, useState } from 'react';
import { supabase } from '@/lib/supabase';
import StatsCard from '@/components/StatsCard';

export default function Metrics() {
  const [metrics, setMetrics] = useState({
    total: 0,
    passed: 0,
    failed: 0,
    avgScore: 0,
    avgDuration: 0,
    byModel: {} as Record<string, { count: number; avgScore: number }>,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchMetrics();
  }, []);

  async function fetchMetrics() {
    if (!supabase) {
      setLoading(false);
      return;
    }
    
    // Get task results
    const { data: results } = await supabase
      .from('task_results')
      .select('score, passed, model_used');

    // Get logs for duration
    const { data: logs } = await supabase
      .from('task_logs')
      .select('duration_ms');

    if (results && results.length > 0) {
      const passed = results.filter(r => r.passed).length;
      const avgScore = results.reduce((sum, r) => sum + r.score, 0) / results.length;
      
      // Group by model
      const byModel: Record<string, { count: number; totalScore: number }> = {};
      results.forEach(r => {
        if (!byModel[r.model_used]) {
          byModel[r.model_used] = { count: 0, totalScore: 0 };
        }
        byModel[r.model_used].count++;
        byModel[r.model_used].totalScore += r.score;
      });

      const modelStats = Object.fromEntries(
        Object.entries(byModel).map(([model, data]) => [
          model,
          { count: data.count, avgScore: data.totalScore / data.count }
        ])
      );

      setMetrics({
        total: results.length,
        passed,
        failed: results.length - passed,
        avgScore: Math.round(avgScore * 10) / 10,
        avgDuration: logs ? Math.round(logs.reduce((sum, l) => sum + (l.duration_ms || 0), 0) / logs.length) : 0,
        byModel: modelStats,
      });
    }
    
    setLoading(false);
  }

  if (loading) {
    return <div className="text-center py-8">Loading...</div>;
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Metrics</h1>
        <p className="text-gray-500 mt-1">Analytics and performance insights</p>
      </div>

      {/* Overview Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <StatsCard title="Total Tasks" value={metrics.total} />
        <StatsCard 
          title="Pass Rate" 
          value={`${metrics.total > 0 ? Math.round((metrics.passed / metrics.total) * 100) : 0}%`}
          trend={metrics.passed / metrics.total >= 0.8 ? 'up' : 'down'}
        />
        <StatsCard title="Avg Score" value={metrics.avgScore} />
        <StatsCard title="Avg Duration" value={`${Math.round(metrics.avgDuration / 1000)}s`} />
      </div>

      {/* Model Comparison */}
      <div>
        <h2 className="text-xl font-bold text-gray-900 mb-4">Model Performance</h2>
        <div className="bg-white rounded-xl border p-6">
          {Object.keys(metrics.byModel).length === 0 ? (
            <div className="text-center text-gray-500 py-8">
              No model data yet
            </div>
          ) : (
            <div className="space-y-4">
              {Object.entries(metrics.byModel).map(([model, data]) => (
                <div key={model} className="flex items-center gap-4">
                  <span className="w-48 font-mono text-sm">{model}</span>
                  <div className="flex-1 bg-gray-100 rounded-full h-4 overflow-hidden">
                    <div 
                      className="bg-blue-500 h-full"
                      style={{ width: `${(data.avgScore / 10) * 100}%` }}
                    />
                  </div>
                  <span className="w-20 text-right font-bold">
                    {Math.round(data.avgScore * 10) / 10}/10
                  </span>
                  <span className="w-20 text-right text-gray-500">
                    {data.count} tasks
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

