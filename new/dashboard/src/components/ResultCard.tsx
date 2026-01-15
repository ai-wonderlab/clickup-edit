'use client';

import { TaskResult } from '@/lib/supabase';
import { CheckCircle, XCircle, Clock } from 'lucide-react';

interface ResultCardProps {
  result: TaskResult;
}

export default function ResultCard({ result }: ResultCardProps) {
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3 min-w-0 flex-1">
          <div className="mt-0.5">
            {result.passed ? (
              <CheckCircle className="w-5 h-5 text-green-500" />
            ) : (
              <XCircle className="w-5 h-5 text-red-500" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-medium text-gray-900 truncate">{result.request}</p>
            <div className="flex items-center gap-3 mt-1 text-sm text-gray-500">
              <span>Score: {result.score}/10</span>
              <span>•</span>
              <span>{result.model_used}</span>
              <span>•</span>
              <span>{result.iterations} iteration{result.iterations !== 1 ? 's' : ''}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-400 flex-shrink-0">
          <Clock className="w-4 h-4" />
          {formatDate(result.created_at)}
        </div>
      </div>
    </div>
  );
}
