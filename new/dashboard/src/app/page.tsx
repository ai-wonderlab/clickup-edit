'use client';

import { useEffect, useState } from 'react';
import { supabase, TaskResult } from '@/lib/supabase';
import StatsCard from '@/components/StatsCard';
import ResultCard from '@/components/ResultCard';
import { Activity, CheckCircle, Clock, TrendingUp } from 'lucide-react';

interface Stats {
  todayTasks: number;
  passRate: number;
  avgScore: number;
  totalTasks: number;
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats>({
    todayTasks: 0,
    passRate: 0,
    avgScore: 0,
    totalTasks: 0,
  });
  const [recentResults, setRecentResults] = useState<TaskResult[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    console.log('[Dashboard] Component mounted');
    console.log('[Dashboard] Supabase client:', supabase ? 'Connected' : 'Not configured');
    fetchData();
  }, []);

  const fetchData = async () => {
    console.log('[Dashboard] Fetching data...');
    
    if (!supabase) {
      console.warn('[Dashboard] Supabase not configured, using mock data');
      setLoading(false);
      return;
    }

    try {
      // Fetch recent results
      console.log('[Dashboard] Querying task_results...');
      const { data: results, error: resultsError } = await supabase
        .from('task_results')
        .select('*')
        .order('created_at', { ascending: false })
        .limit(10);

      if (resultsError) {
        console.error('[Dashboard] Error fetching results:', resultsError);
        throw resultsError;
      }

      console.log('[Dashboard] Fetched results:', results?.length || 0);
      setRecentResults(results || []);

      // Calculate stats
      if (results && results.length > 0) {
        const passed = results.filter((r) => r.passed).length;
        const avgScore = results.reduce((acc, r) => acc + (r.score || 0), 0) / results.length;
        const today = new Date().toDateString();
        const todayTasks = results.filter(
          (r) => new Date(r.created_at).toDateString() === today
        ).length;

        const newStats = {
          todayTasks,
          passRate: Math.round((passed / results.length) * 100),
          avgScore: Math.round(avgScore * 10) / 10,
          totalTasks: results.length,
        };
        
        console.log('[Dashboard] Calculated stats:', newStats);
        setStats(newStats);
      }
    } catch (err) {
      console.error('[Dashboard] Error:', err);
    } finally {
      setLoading(false);
      console.log('[Dashboard] Loading complete');
    }
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
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-600 mt-1">Overview of your image editing pipeline</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatsCard
          title="Today's Tasks"
          value={stats.todayTasks}
          icon={<Activity className="w-5 h-5" />}
          trend={stats.todayTasks > 0 ? 'up' : undefined}
        />
        <StatsCard
          title="Pass Rate"
          value={`${stats.passRate}%`}
          icon={<CheckCircle className="w-5 h-5" />}
          trend={stats.passRate >= 80 ? 'up' : stats.passRate < 50 ? 'down' : undefined}
          subtitle={stats.passRate < 50 ? 'Needs attention' : undefined}
        />
        <StatsCard
          title="Avg Score"
          value={stats.avgScore}
          icon={<TrendingUp className="w-5 h-5" />}
        />
        <StatsCard
          title="Total Tasks"
          value={stats.totalTasks}
          icon={<Clock className="w-5 h-5" />}
        />
      </div>

      {/* Recent Results */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Recent Results</h2>
        {recentResults.length === 0 ? (
          <div className="bg-white border border-gray-200 rounded-lg p-8 text-center text-gray-500">
            No results yet. Tasks will appear here when processed.
          </div>
        ) : (
          <div className="space-y-3">
            {recentResults.map((result) => (
              <ResultCard key={result.id} result={result} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
