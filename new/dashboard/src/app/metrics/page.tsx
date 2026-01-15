'use client';

import { useEffect, useState } from 'react';
import { supabase } from '@/lib/supabase';
import StatsCard from '@/components/StatsCard';
import { BarChart3, TrendingUp, Clock, CheckCircle, XCircle, Zap, ThumbsUp, ThumbsDown } from 'lucide-react';
import Toast, { useToast } from '@/components/Toast';

interface Metrics {
  totalTasks: number;
  passedTasks: number;
  failedTasks: number;
  avgScore: number;
  avgIterations: number;
  avgDuration: number;
  modelUsage: Record<string, number>;
  // Satisfaction metrics
  likeCount: number;
  dislikeCount: number;
  satisfactionRate: number;
}

export default function Metrics() {
  const [metrics, setMetrics] = useState<Metrics>({
    totalTasks: 0,
    passedTasks: 0,
    failedTasks: 0,
    avgScore: 0,
    avgIterations: 0,
    avgDuration: 0,
    modelUsage: {},
    likeCount: 0,
    dislikeCount: 0,
    satisfactionRate: 0,
  });
  const [loading, setLoading] = useState(true);
  const { toasts, addToast, removeToast } = useToast();

  useEffect(() => {
    console.log('[Metrics] Component mounted');
    fetchMetrics();
  }, []);

  const fetchMetrics = async () => {
    console.log('[Metrics] Fetching metrics...');
    
    if (!supabase) {
      console.warn('[Metrics] Supabase not configured');
      addToast('info', 'Using mock metrics (no database)');
      setLoading(false);
      return;
    }

    try {
      const { data, error } = await supabase
        .from('task_results')
        .select('*');

      if (error) {
        console.error('[Metrics] Error:', error);
        throw error;
      }

      console.log('[Metrics] Fetched results:', data?.length || 0);

      if (data && data.length > 0) {
        const passed = data.filter((r) => r.passed).length;
        const avgScore = data.reduce((acc, r) => acc + (r.score || 0), 0) / data.length;
        const avgIterations = data.reduce((acc, r) => acc + (r.iterations || 0), 0) / data.length;

        // Count model usage
        const modelUsage: Record<string, number> = {};
        data.forEach((r) => {
          if (r.model_used) {
            modelUsage[r.model_used] = (modelUsage[r.model_used] || 0) + 1;
          }
        });

        // Calculate satisfaction metrics
        const likeCount = data.filter((r) => r.user_feedback === 'Like').length;
        const dislikeCount = data.filter((r) => r.user_feedback === 'Dislike').length;
        const feedbackTotal = likeCount + dislikeCount;
        const satisfactionRate = feedbackTotal > 0 ? Math.round((likeCount / feedbackTotal) * 100) : 0;

        const newMetrics = {
          totalTasks: data.length,
          passedTasks: passed,
          failedTasks: data.length - passed,
          avgScore: Math.round(avgScore * 10) / 10,
          avgIterations: Math.round(avgIterations * 10) / 10,
          avgDuration: 0,
          modelUsage,
          likeCount,
          dislikeCount,
          satisfactionRate,
        };

        console.log('[Metrics] Calculated:', newMetrics);
        setMetrics(newMetrics);
      }

      addToast('success', 'Metrics loaded');
    } catch (err) {
      console.error('[Metrics] Error:', err);
      addToast('error', 'Failed to load metrics');
    } finally {
      setLoading(false);
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
        <h1 className="text-2xl font-bold text-gray-900">Metrics</h1>
        <p className="text-gray-600 mt-1">Pipeline performance analytics</p>
      </div>

      {/* Overview Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatsCard
          title="Total Tasks"
          value={metrics.totalTasks}
          icon={<BarChart3 className="w-5 h-5" />}
        />
        <StatsCard
          title="Passed"
          value={metrics.passedTasks}
          icon={<CheckCircle className="w-5 h-5" />}
          trend="up"
        />
        <StatsCard
          title="Failed"
          value={metrics.failedTasks}
          icon={<XCircle className="w-5 h-5" />}
          trend={metrics.failedTasks > 0 ? 'down' : undefined}
        />
        <StatsCard
          title="Pass Rate"
          value={`${metrics.totalTasks > 0 ? Math.round((metrics.passedTasks / metrics.totalTasks) * 100) : 0}%`}
          icon={<Clock className="w-5 h-5" />}
        />
      </div>

      {/* Performance Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <StatsCard
          title="Avg Score"
          value={`${metrics.avgScore}/10`}
          icon={<TrendingUp className="w-5 h-5" />}
        />
        <StatsCard
          title="Avg Iterations"
          value={metrics.avgIterations}
          icon={<Zap className="w-5 h-5" />}
        />
        <StatsCard
          title="Satisfaction Rate"
          value={`${metrics.satisfactionRate}%`}
          icon={<ThumbsUp className="w-5 h-5" />}
          trend={metrics.satisfactionRate >= 80 ? 'up' : metrics.satisfactionRate < 50 ? 'down' : undefined}
          subtitle={`${metrics.likeCount} likes, ${metrics.dislikeCount} dislikes`}
        />
      </div>

      {/* Feedback Breakdown */}
      {(metrics.likeCount > 0 || metrics.dislikeCount > 0) && (
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">User Feedback</h2>
          <div className="flex items-center gap-8">
            <div className="flex items-center gap-3">
              <div className="p-3 bg-green-100 rounded-lg">
                <ThumbsUp className="w-6 h-6 text-green-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900">{metrics.likeCount}</p>
                <p className="text-sm text-gray-500">Likes</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="p-3 bg-red-100 rounded-lg">
                <ThumbsDown className="w-6 h-6 text-red-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900">{metrics.dislikeCount}</p>
                <p className="text-sm text-gray-500">Dislikes</p>
              </div>
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm text-gray-500">Satisfaction</span>
                <span className="text-sm font-medium text-gray-700">{metrics.satisfactionRate}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-3">
                <div
                  className="bg-green-500 h-3 rounded-full transition-all"
                  style={{ width: `${metrics.satisfactionRate}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Model Usage */}
      {Object.keys(metrics.modelUsage).length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Model Usage</h2>
          <div className="space-y-3">
            {Object.entries(metrics.modelUsage).map(([model, count]) => (
              <div key={model} className="flex items-center gap-4">
                <span className="text-sm text-gray-600 w-48 truncate">{model}</span>
                <div className="flex-1 bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-blue-600 h-2 rounded-full"
                    style={{
                      width: `${(count / metrics.totalTasks) * 100}%`,
                    }}
                  />
                </div>
                <span className="text-sm text-gray-500 w-16 text-right">{count} tasks</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <Toast toasts={toasts} removeToast={removeToast} />
    </div>
  );
}
