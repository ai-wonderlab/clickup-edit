'use client';

import { useState } from 'react';
import Editor from '@monaco-editor/react';
import { Save, X } from 'lucide-react';

interface PromptEditorProps {
  promptId: string;
  name: string;
  initialContent: string;
  onSave: (content: string) => Promise<void>;
  onClose: () => void;
}

export default function PromptEditor({ 
  promptId, 
  name, 
  initialContent, 
  onSave, 
  onClose 
}: PromptEditorProps) {
  const [content, setContent] = useState(initialContent);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await onSave(content);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl w-[90vw] h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <div>
            <h2 className="text-xl font-bold text-gray-900">{name}</h2>
            <span className="text-sm text-gray-500">{promptId}</span>
          </div>
          <div className="flex items-center gap-3">
            {error && (
              <span className="text-red-500 text-sm">{error}</span>
            )}
            <button
              onClick={onClose}
              className="p-2 text-gray-500 hover:text-gray-700"
            >
              <X size={20} />
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              <Save size={16} />
              {saving ? 'Saving...' : 'Save'}
            </button>
          </div>
        </div>
        
        {/* Editor */}
        <div className="flex-1">
          <Editor
            height="100%"
            defaultLanguage="markdown"
            value={content}
            onChange={(value) => setContent(value || '')}
            theme="vs-light"
            options={{
              minimap: { enabled: false },
              fontSize: 14,
              lineNumbers: 'on',
              wordWrap: 'on',
              padding: { top: 16 },
            }}
          />
        </div>
        
        {/* Footer */}
        <div className="px-6 py-3 border-t bg-gray-50 text-sm text-gray-500">
          Lines: {content.split('\n').length} • Characters: {content.length}
        </div>
      </div>
    </div>
  );
}

