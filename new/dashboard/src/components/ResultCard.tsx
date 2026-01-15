import { TaskResult } from '@/lib/supabase';
import { CheckCircle, XCircle, Clock, ThumbsUp, ThumbsDown } from 'lucide-react';

interface ResultCardProps {
  result: TaskResult;
  onClick?: () => void;
}

export default function ResultCard({ result, onClick }: ResultCardProps) {
  const passed = result.passed;
  const timeAgo = getTimeAgo(result.created_at);
  
  return (
    <div 
      className={`p-4 rounded-lg border cursor-pointer transition-all hover:shadow-md ${
        passed ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'
      }`}
      onClick={onClick}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {passed ? (
            <CheckCircle className="text-green-500" size={24} />
          ) : (
            <XCircle className="text-red-500" size={24} />
          )}
          <div>
            <div className="font-medium text-gray-900">
              Task #{result.task_id.slice(0, 8)}
            </div>
            <div className="text-sm text-gray-500 truncate max-w-md">
              {result.request || 'No request text'}
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-4 text-sm">
          <span className={`font-bold ${passed ? 'text-green-600' : 'text-red-600'}`}>
            {result.score}/10
          </span>
          <span className="text-gray-500">{result.model_used}</span>
          <span className="text-gray-400 flex items-center gap-1">
            <Clock size={14} />
            {timeAgo}
          </span>
          {result.user_feedback && (
            result.user_feedback === 'good' ? (
              <ThumbsUp className="text-green-500" size={16} />
            ) : (
              <ThumbsDown className="text-red-500" size={16} />
            )
          )}
        </div>
      </div>
    </div>
  );
}

function getTimeAgo(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);
  
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

