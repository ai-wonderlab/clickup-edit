'use client';

import { useState, useEffect } from 'react';
import { Prompt } from '@/lib/supabase';
import { X, Save, RotateCcw, Copy, Check } from 'lucide-react';

interface PromptEditorProps {
  prompt: Prompt;
  onSave: (prompt: Prompt) => void;
  onClose: () => void;
  saving?: boolean;
}

export default function PromptEditor({ prompt, onSave, onClose, saving }: PromptEditorProps) {
  const [content, setContent] = useState(prompt.content);
  const [copied, setCopied] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    console.log('[PromptEditor] Opened for:', prompt.prompt_id);
    setHasChanges(content !== prompt.content);
  }, [content, prompt.content, prompt.prompt_id]);

  const handleSave = () => {
    console.log('[PromptEditor] Saving changes...');
    onSave({ ...prompt, content });
  };

  const handleReset = () => {
    console.log('[PromptEditor] Resetting content');
    setContent(prompt.content);
  };

  const handleCopy = async () => {
    console.log('[PromptEditor] Copying to clipboard');
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        console.log('[PromptEditor] Escape pressed, closing');
        onClose();
      }
      if (e.key === 's' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        console.log('[PromptEditor] Cmd+S pressed, saving');
        handleSave();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [content]);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <div className="flex items-center gap-3">
            <span className="font-mono text-lg font-bold text-blue-600">
              {prompt.prompt_id}
            </span>
            <span className="text-gray-600">{prompt.name}</span>
            <span className="px-2 py-1 bg-gray-100 rounded text-xs text-gray-500">
              {prompt.category}
            </span>
            {hasChanges && (
              <span className="px-2 py-1 bg-yellow-100 text-yellow-700 rounded text-xs">
                Unsaved changes
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Editor */}
        <div className="flex-1 p-4 overflow-hidden">
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="w-full h-full min-h-[400px] p-4 border border-gray-200 rounded-lg font-mono text-sm resize-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="Enter prompt content..."
          />
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t border-gray-200 bg-gray-50">
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="flex items-center gap-2 px-3 py-2 text-gray-600 hover:bg-gray-200 rounded-lg transition-colors"
            >
              {copied ? (
                <>
                  <Check className="w-4 h-4 text-green-500" />
                  <span className="text-green-600">Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="w-4 h-4" />
                  Copy
                </>
              )}
            </button>
            <button
              onClick={handleReset}
              disabled={!hasChanges}
              className="flex items-center gap-2 px-3 py-2 text-gray-600 hover:bg-gray-200 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RotateCcw className="w-4 h-4" />
              Reset
            </button>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400 mr-2">
              ⌘S to save
            </span>
            <button
              onClick={onClose}
              className="px-4 py-2 text-gray-600 hover:bg-gray-200 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !hasChanges}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                  Saving...
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  Save Changes
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
