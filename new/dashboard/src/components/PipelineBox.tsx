'use client';

import { ReactNode } from 'react';

interface PipelineBoxProps {
  title: string;
  description?: string;
  children?: ReactNode;
  status?: 'active' | 'completed' | 'pending';
}

export default function PipelineBox({ title, description, children, status = 'pending' }: PipelineBoxProps) {
  const statusColors = {
    active: 'border-blue-500 bg-blue-50',
    completed: 'border-green-500 bg-green-50',
    pending: 'border-gray-200 bg-white',
  };

  return (
    <div className={`border-2 rounded-lg p-4 transition-all ${statusColors[status]}`}>
      <h3 className="font-semibold text-gray-900">{title}</h3>
      {description && <p className="text-sm text-gray-500 mt-1">{description}</p>}
      {children && <div className="mt-3">{children}</div>}
    </div>
  );
}
