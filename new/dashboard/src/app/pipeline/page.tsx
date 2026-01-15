'use client';

import { useState, useEffect } from 'react';
import { supabase, Prompt } from '@/lib/supabase';
import PromptEditor from '@/components/PromptEditor';
import Toast, { useToast } from '@/components/Toast';
import { ChevronDown, ChevronRight, RotateCcw } from 'lucide-react';

interface PipelineStep {
  id: string;
  name: string;
  description: string;
  promptIds: string[];
}

const PIPELINE_STEPS: PipelineStep[] = [
  {
    id: 'enhancement',
    name: 'Enhancement',
    description: 'Enhance and analyze user requests',
    promptIds: ['P1', 'P2', 'P3'],
  },
  {
    id: 'generation',
    name: 'Generation',
    description: 'Generate images using AI models',
    promptIds: ['P4', 'P10', 'P11', 'P12'],
  },
  {
    id: 'validation',
    name: 'Validation',
    description: 'Validate generated images',
    promptIds: ['P5', 'P6', 'P7'],
  },
  {
    id: 'iteration',
    name: 'Iteration Loop',
    description: 'Refine based on validation feedback',
    promptIds: ['P8', 'P15'],
  },
  {
    id: 'fallback',
    name: 'Fallback Strategies',
    description: 'Sequential and hybrid fallback options',
    promptIds: ['P16', 'P17'],
  },
];

export default function PipelinePage() {
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set());
  const [selectedPrompt, setSelectedPrompt] = useState<Prompt | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const { toasts, addToast, removeToast } = useToast();

  useEffect(() => {
    console.log('[Pipeline] Component mounted');
    fetchPrompts();
  }, []);

  const fetchPrompts = async () => {
    console.log('[Pipeline] Fetching prompts...');
    
    if (!supabase) {
      console.warn('[Pipeline] Supabase not configured');
      addToast('error', 'Supabase not configured');
      setLoading(false);
      return;
    }

    try {
      const { data, error } = await supabase
        .from('prompts')
        .select('*')
        .order('prompt_id');

      if (error) {
        console.error('[Pipeline] Error fetching prompts:', error);
        throw error;
      }
      
      console.log('[Pipeline] Fetched prompts:', data?.length || 0);
      setPrompts(data || []);
      addToast('info', `Loaded ${data?.length || 0} prompts`);
    } catch (err) {
      console.error('[Pipeline] Error:', err);
      addToast('error', 'Failed to load prompts');
    } finally {
      setLoading(false);
    }
  };

  const toggleStep = (stepId: string) => {
    console.log('[Pipeline] Toggle step:', stepId);
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(stepId)) {
        next.delete(stepId);
      } else {
        next.add(stepId);
      }
      return next;
    });
  };

  const getPromptsForStep = (promptIds: string[]) => {
    return prompts.filter((p) => promptIds.includes(p.prompt_id));
  };

  const handlePromptSelect = (prompt: Prompt) => {
    console.log('[Pipeline] Selected prompt:', prompt.prompt_id);
    setSelectedPrompt(prompt);
    addToast('info', `Editing ${prompt.prompt_id}: ${prompt.name}`);
  };

  const handlePromptSave = async (updatedPrompt: Prompt) => {
    console.log('[Pipeline] Saving prompt:', updatedPrompt.prompt_id);
    
    if (!supabase) return;

    setSaving(true);
    try {
      // Save to prompt_history first
      console.log('[Pipeline] Adding to history...');
      await supabase.from('prompt_history').insert({
        prompt_id: updatedPrompt.prompt_id,
        content: updatedPrompt.content,
        version: 1,
      });

      // Update the prompt
      console.log('[Pipeline] Updating prompt...');
      const { error } = await supabase
        .from('prompts')
        .update({
          content: updatedPrompt.content,
          updated_at: new Date().toISOString(),
        })
        .eq('id', updatedPrompt.id);

      if (error) throw error;

      setPrompts((prev) =>
        prev.map((p) => (p.id === updatedPrompt.id ? updatedPrompt : p))
      );
      setSelectedPrompt(null);
      console.log('[Pipeline] Save successful');
      addToast('success', `Saved ${updatedPrompt.prompt_id} successfully`);
    } catch (err) {
      console.error('[Pipeline] Save error:', err);
      addToast('error', 'Failed to save prompt');
    } finally {
      setSaving(false);
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Pipeline Configuration</h1>
          <p className="text-gray-600 mt-1">Click on each step to view and edit prompts</p>
        </div>
        <button
          onClick={fetchPrompts}
          className="flex items-center gap-2 px-4 py-2 text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <RotateCcw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Pipeline Flow */}
      <div className="space-y-4">
        {PIPELINE_STEPS.map((step, index) => (
          <div key={step.id} className="border border-gray-200 rounded-lg overflow-hidden bg-white">
            {/* Step Header - Clickable */}
            <button
              onClick={() => toggleStep(step.id)}
              className="w-full flex items-center justify-between p-4 bg-gray-50 hover:bg-gray-100 transition-colors"
            >
              <div className="flex items-center gap-4">
                <div className="flex items-center justify-center w-8 h-8 rounded-full bg-blue-600 text-white font-semibold text-sm">
                  {index + 1}
                </div>
                <div className="text-left">
                  <h3 className="font-semibold text-gray-900">{step.name}</h3>
                  <p className="text-sm text-gray-500">{step.description}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm text-gray-400">
                  {step.promptIds.length} prompts
                </span>
                {expandedSteps.has(step.id) ? (
                  <ChevronDown className="w-5 h-5 text-gray-400" />
                ) : (
                  <ChevronRight className="w-5 h-5 text-gray-400" />
                )}
              </div>
            </button>

            {/* Expanded Content - Prompts */}
            {expandedSteps.has(step.id) && (
              <div className="p-4 border-t border-gray-200">
                <div className="grid gap-3">
                  {getPromptsForStep(step.promptIds).length === 0 ? (
                    <p className="text-gray-500 text-sm py-4 text-center">
                      No prompts found for IDs: {step.promptIds.join(', ')}
                    </p>
                  ) : (
                    getPromptsForStep(step.promptIds).map((prompt) => (
                      <div
                        key={prompt.id}
                        onClick={() => handlePromptSelect(prompt)}
                        className="p-4 border border-gray-200 rounded-lg hover:border-blue-300 hover:bg-blue-50 cursor-pointer transition-all"
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="font-mono text-sm font-semibold text-blue-600">
                                {prompt.prompt_id}
                              </span>
                              <span className="font-medium text-gray-900">
                                {prompt.name}
                              </span>
                            </div>
                            <p className="text-sm text-gray-500 line-clamp-2">
                              {prompt.content.substring(0, 150)}...
                            </p>
                          </div>
                          <span className="text-xs text-gray-400 whitespace-nowrap">
                            {prompt.category}
                          </span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Prompt Editor Modal */}
      {selectedPrompt && (
        <PromptEditor
          prompt={selectedPrompt}
          onSave={handlePromptSave}
          onClose={() => {
            console.log('[Pipeline] Editor closed');
            setSelectedPrompt(null);
          }}
          saving={saving}
        />
      )}

      <Toast toasts={toasts} removeToast={removeToast} />
    </div>
  );
}
