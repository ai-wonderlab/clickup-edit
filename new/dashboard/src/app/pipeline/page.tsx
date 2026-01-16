'use client';

import { useState, useEffect } from 'react';
import { supabase, Prompt } from '@/lib/supabase';
import PromptEditor from '@/components/PromptEditor';
import Toast, { useToast } from '@/components/Toast';
import { RotateCcw, Sparkles, Image, CheckCircle, Palette, Brain, AlertTriangle, Share2 } from 'lucide-react';

// Categories matching Supabase database exactly
const CATEGORIES = [
  {
    id: 'enhancement',
    name: 'Enhancement',
    description: 'Enhance and analyze user requests (P1, P2, P3)',
    icon: Sparkles,
    color: 'blue',
  },
  {
    id: 'generation',
    name: 'Generation',
    description: 'Generate images using AI models (P10, P11)',
    icon: Image,
    color: 'purple',
  },
  {
    id: 'validation',
    name: 'Validation',
    description: 'Validate generated images (P4, P5, P6, P7)',
    icon: CheckCircle,
    color: 'green',
  },
  {
    id: 'brand',
    name: 'Brand',
    description: 'Brand analysis and styling (P8, P9)',
    icon: Palette,
    color: 'pink',
  },
  {
    id: 'deep_research',
    name: 'Deep Research',
    description: 'Model-specific research prompts (P15, P16)',
    icon: Brain,
    color: 'indigo',
  },
  {
    id: 'fallback',
    name: 'Fallback',
    description: 'Fallback strategies (P14)',
    icon: AlertTriangle,
    color: 'orange',
  },
  {
    id: 'shared',
    name: 'Shared',
    description: 'Shared resources like fonts guide (P17)',
    icon: Share2,
    color: 'gray',
  },
];

// Color mapping for category badges
const CATEGORY_COLORS: Record<string, string> = {
  blue: 'bg-blue-100 text-blue-700 border-blue-200',
  purple: 'bg-purple-100 text-purple-700 border-purple-200',
  green: 'bg-green-100 text-green-700 border-green-200',
  pink: 'bg-pink-100 text-pink-700 border-pink-200',
  indigo: 'bg-indigo-100 text-indigo-700 border-indigo-200',
  orange: 'bg-orange-100 text-orange-700 border-orange-200',
  gray: 'bg-gray-100 text-gray-700 border-gray-200',
};

const TAB_COLORS: Record<string, { active: string; inactive: string }> = {
  blue: { active: 'bg-blue-600 text-white', inactive: 'text-blue-600 hover:bg-blue-50' },
  purple: { active: 'bg-purple-600 text-white', inactive: 'text-purple-600 hover:bg-purple-50' },
  green: { active: 'bg-green-600 text-white', inactive: 'text-green-600 hover:bg-green-50' },
  pink: { active: 'bg-pink-600 text-white', inactive: 'text-pink-600 hover:bg-pink-50' },
  indigo: { active: 'bg-indigo-600 text-white', inactive: 'text-indigo-600 hover:bg-indigo-50' },
  orange: { active: 'bg-orange-600 text-white', inactive: 'text-orange-600 hover:bg-orange-50' },
  gray: { active: 'bg-gray-600 text-white', inactive: 'text-gray-600 hover:bg-gray-50' },
};

export default function PipelinePage() {
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [activeCategory, setActiveCategory] = useState<string>('enhancement');
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

  // Filter prompts by category from database
  const getPromptsForCategory = (categoryId: string) => {
    return prompts.filter((p) => p.category === categoryId);
  };

  // Get count of prompts per category
  const getCategoryCount = (categoryId: string) => {
    return prompts.filter((p) => p.category === categoryId).length;
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

  const activeTab = CATEGORIES.find((c) => c.id === activeCategory);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Pipeline Configuration</h1>
          <p className="text-gray-600 mt-1">Manage prompts by category - {prompts.length} total prompts</p>
        </div>
        <button
          onClick={fetchPrompts}
          className="flex items-center gap-2 px-4 py-2 text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <RotateCcw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Category Tabs */}
      <div className="border-b border-gray-200">
        <div className="flex flex-wrap gap-2 pb-4">
          {CATEGORIES.map((category) => {
            const Icon = category.icon;
            const count = getCategoryCount(category.id);
            const isActive = activeCategory === category.id;
            const colors = TAB_COLORS[category.color];
            
            return (
              <button
                key={category.id}
                onClick={() => setActiveCategory(category.id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all ${
                  isActive ? colors.active : colors.inactive
                } border ${isActive ? 'border-transparent' : 'border-gray-200'}`}
              >
                <Icon className="w-4 h-4" />
                <span>{category.name}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  isActive ? 'bg-white/20' : 'bg-gray-100'
                }`}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Active Category Info */}
      {activeTab && (
        <div className={`p-4 rounded-lg border ${CATEGORY_COLORS[activeTab.color]}`}>
          <div className="flex items-center gap-3">
            <activeTab.icon className="w-5 h-5" />
            <div>
              <h2 className="font-semibold">{activeTab.name}</h2>
              <p className="text-sm opacity-80">{activeTab.description}</p>
            </div>
          </div>
        </div>
      )}

      {/* Prompts Grid */}
      <div className="grid gap-4">
        {getPromptsForCategory(activeCategory).length === 0 ? (
          <div className="text-center py-12 bg-gray-50 rounded-lg border border-dashed border-gray-300">
            <p className="text-gray-500">No prompts found in category: {activeCategory}</p>
          </div>
        ) : (
          getPromptsForCategory(activeCategory).map((prompt) => (
            <div
              key={prompt.id}
              onClick={() => handlePromptSelect(prompt)}
              className="p-5 bg-white border border-gray-200 rounded-lg hover:border-blue-300 hover:shadow-md cursor-pointer transition-all"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-2">
                    <span className="font-mono text-sm font-bold px-2 py-1 bg-blue-100 text-blue-700 rounded">
                      {prompt.prompt_id}
                    </span>
                    <span className="font-semibold text-gray-900">
                      {prompt.name}
                    </span>
                  </div>
                  <p className="text-sm text-gray-500 line-clamp-3">
                    {prompt.content.substring(0, 200)}...
                  </p>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <span className={`text-xs px-2 py-1 rounded border ${CATEGORY_COLORS[activeTab?.color || 'gray']}`}>
                    {prompt.category}
                  </span>
                  <span className="text-xs text-gray-400">
                    {prompt.content.length.toLocaleString()} chars
                  </span>
                </div>
              </div>
            </div>
          ))
        )}
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
