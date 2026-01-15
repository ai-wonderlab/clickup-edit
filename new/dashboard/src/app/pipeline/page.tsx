'use client';

import { useState, useEffect } from 'react';
import { supabase, Prompt } from '@/lib/supabase';
import PipelineBox from '@/components/PipelineBox';
import PromptEditor from '@/components/PromptEditor';

const pipelineConfig = [
  {
    name: 'Enhancer',
    icon: '🧠',
    description: 'Enhances user prompts before sending to image model',
    prompts: ['P1', 'P2', 'P3'],
    href: '/pipeline?phase=enhancer',
  },
  {
    name: 'Generator',
    icon: '🎨',
    description: 'Generates images using WaveSpeed AI models',
    prompts: [],
    href: '/pipeline?phase=generator',
  },
  {
    name: 'Validator',
    icon: '✓',
    description: 'Validates generated images against requirements',
    prompts: ['P4', 'P5', 'P6', 'P7'],
    href: '/pipeline?phase=validator',
  },
];

export default function Pipeline() {
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [editingPrompt, setEditingPrompt] = useState<Prompt | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPrompts();
  }, []);

  async function fetchPrompts() {
    if (!supabase) {
      setLoading(false);
      return;
    }
    
    const { data } = await supabase
      .from('prompts')
      .select('*')
      .order('prompt_id');
    
    if (data) setPrompts(data);
    setLoading(false);
  }

  async function savePrompt(content: string) {
    if (!editingPrompt || !supabase) return;
    
    const { error } = await supabase
      .from('prompts')
      .update({ content, updated_at: new Date().toISOString() })
      .eq('prompt_id', editingPrompt.prompt_id);
    
    if (error) throw error;
    
    await fetchPrompts();
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Pipeline</h1>
        <p className="text-gray-500 mt-1">Configure your image editing pipeline</p>
      </div>

      {/* Pipeline Visualization */}
      <div className="flex items-center justify-center gap-4">
        {pipelineConfig.map((phase, index) => (
          <div key={phase.name} className="flex items-center">
            <PipelineBox {...phase} />
            {index < pipelineConfig.length - 1 && (
              <div className="text-4xl text-gray-300 mx-4">→</div>
            )}
          </div>
        ))}
      </div>

      {/* Prompts List */}
      <div>
        <h2 className="text-xl font-bold text-gray-900 mb-4">All Prompts</h2>
        {loading ? (
          <div className="text-center py-8">Loading...</div>
        ) : prompts.length === 0 ? (
          <div className="text-center py-12 text-gray-500 bg-white rounded-xl border">
            No prompts in database. Add prompts via SQL or import from YAML.
          </div>
        ) : (
          <div className="grid gap-4">
            {prompts.map((prompt) => (
              <div
                key={prompt.id}
                className="p-4 bg-white rounded-lg border hover:border-blue-400 cursor-pointer transition-all"
                onClick={() => setEditingPrompt(prompt)}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <span className="font-mono text-blue-600 font-bold mr-3">
                      {prompt.prompt_id}
                    </span>
                    <span className="font-medium text-gray-900">{prompt.name}</span>
                  </div>
                  <span className="text-sm text-gray-500 bg-gray-100 px-2 py-1 rounded">
                    {prompt.category}
                  </span>
                </div>
                <div className="text-sm text-gray-500 mt-2 truncate">
                  {prompt.content.slice(0, 100)}...
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Editor Modal */}
      {editingPrompt && (
        <PromptEditor
          promptId={editingPrompt.prompt_id}
          name={editingPrompt.name}
          initialContent={editingPrompt.content}
          onSave={savePrompt}
          onClose={() => setEditingPrompt(null)}
        />
      )}
    </div>
  );
}

