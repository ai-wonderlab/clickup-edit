'use client';

import { useEffect, useState } from 'react';
import { supabase, Parameter } from '@/lib/supabase';
import { Save, RotateCcw, Info } from 'lucide-react';
import Toast, { useToast } from '@/components/Toast';

// Only show parameters that are actually used by the backend
const DEFAULT_PARAMETERS: Omit<Parameter, 'id'>[] = [
  { key: 'MAX_ITERATIONS', value: '3', type: 'int', min_value: 1, max_value: 10, updated_at: '' },
  { key: 'MAX_STEP_ATTEMPTS', value: '2', type: 'int', min_value: 1, max_value: 5, updated_at: '' },
  { key: 'VALIDATION_PASS_THRESHOLD', value: '8', type: 'int', min_value: 1, max_value: 10, updated_at: '' },
];

const PARAMETER_DESCRIPTIONS: Record<string, string> = {
  MAX_ITERATIONS: 'Maximum refinement iterations before fallback (used in orchestrator.py)',
  MAX_STEP_ATTEMPTS: 'Retry attempts per sequential step (used in orchestrator.py)',
  VALIDATION_PASS_THRESHOLD: 'Minimum score (1-10) to pass validation (used in orchestrator.py)',
};

export default function Settings() {
  const [parameters, setParameters] = useState<Parameter[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [changes, setChanges] = useState<Record<string, string>>({});
  const { toasts, addToast, removeToast } = useToast();

  useEffect(() => {
    console.log('[Settings] Component mounted');
    fetchParameters();
  }, []);

  const fetchParameters = async () => {
    console.log('[Settings] Fetching parameters...');
    
    if (!supabase) {
      console.warn('[Settings] Supabase not configured, using defaults');
      setParameters(DEFAULT_PARAMETERS.map((p, i) => ({ ...p, id: `default-${i}` })));
      addToast('info', 'Using default parameters (no database)');
      setLoading(false);
      return;
    }

    try {
      const { data, error } = await supabase
        .from('parameters')
        .select('*')
        .order('key');

      if (error) {
        console.error('[Settings] Error fetching:', error);
        throw error;
      }

      console.log('[Settings] Fetched from DB:', data?.length || 0);

      // Merge with defaults to ensure all 8 are present
      const merged = DEFAULT_PARAMETERS.map((def, i) => {
        const existing = data?.find((d) => d.key === def.key);
        if (existing) {
          console.log('[Settings] Found in DB:', def.key, '=', existing.value);
        } else {
          console.log('[Settings] Using default:', def.key, '=', def.value);
        }
        return existing || { ...def, id: `default-${i}` };
      });

      setParameters(merged);
      addToast('success', `Loaded ${merged.length} parameters`);
    } catch (err) {
      console.error('[Settings] Error:', err);
      addToast('error', 'Failed to load parameters');
      setParameters(DEFAULT_PARAMETERS.map((p, i) => ({ ...p, id: `default-${i}` })));
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (key: string, value: string) => {
    console.log('[Settings] Changed:', key, '=', value);
    setChanges((prev) => ({ ...prev, [key]: value }));
  };

  const getValue = (param: Parameter) => {
    return changes[param.key] ?? param.value;
  };

  const handleSaveAll = async () => {
    console.log('[Settings] Saving all changes:', changes);
    
    if (!supabase || Object.keys(changes).length === 0) {
      addToast('info', 'No changes to save');
      return;
    }

    setSaving(true);
    try {
      for (const [key, value] of Object.entries(changes)) {
        const param = parameters.find((p) => p.key === key);
        
        if (param && !param.id.startsWith('default-')) {
          console.log('[Settings] Updating existing:', key);
          const { error } = await supabase
            .from('parameters')
            .update({ value, updated_at: new Date().toISOString() })
            .eq('id', param.id);

          if (error) throw error;
        } else {
          console.log('[Settings] Inserting new:', key);
          const def = DEFAULT_PARAMETERS.find((d) => d.key === key);
          const { error } = await supabase.from('parameters').insert({
            key,
            value,
            type: def?.type || 'string',
            min_value: def?.min_value,
            max_value: def?.max_value,
          });

          if (error) throw error;
        }
      }

      console.log('[Settings] Save successful');
      addToast('success', `Saved ${Object.keys(changes).length} parameter(s)`);
      setChanges({});
      fetchParameters();
    } catch (err) {
      console.error('[Settings] Save error:', err);
      addToast('error', 'Failed to save parameters');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    console.log('[Settings] Resetting changes');
    setChanges({});
    addToast('info', 'Changes reset');
  };

  const hasChanges = Object.keys(changes).length > 0;

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
          <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
          <p className="text-gray-600 mt-1">Configure pipeline parameters ({parameters.length} total)</p>
        </div>
        <div className="flex items-center gap-2">
          {hasChanges && (
            <button
              onClick={handleReset}
              className="flex items-center gap-2 px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <RotateCcw className="w-4 h-4" />
              Reset
            </button>
          )}
          <button
            onClick={handleSaveAll}
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
                Save All
              </>
            )}
          </button>
        </div>
      </div>

      {/* Parameters Grid */}
      <div className="grid gap-4 md:grid-cols-2">
        {parameters.map((param) => (
          <div
            key={param.key}
            className={`p-4 border rounded-lg bg-white transition-all ${
              changes[param.key] !== undefined
                ? 'border-blue-300 bg-blue-50'
                : 'border-gray-200'
            }`}
          >
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="font-semibold text-gray-900 font-mono text-sm">
                  {param.key}
                </h3>
                <p className="text-xs text-gray-500 mt-1 flex items-center gap-1">
                  <Info className="w-3 h-3" />
                  {PARAMETER_DESCRIPTIONS[param.key] || 'No description'}
                </p>
              </div>
              <span className="text-xs px-2 py-1 bg-gray-100 rounded text-gray-500">
                {param.type}
              </span>
            </div>

            <div className="flex items-center gap-4">
              <input
                type="range"
                min={param.min_value ?? 0}
                max={param.max_value ?? 100}
                step={param.type === 'float' ? 0.5 : 1}
                value={Number(getValue(param))}
                onChange={(e) => handleChange(param.key, e.target.value)}
                className="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
              />
              <input
                type="number"
                min={param.min_value ?? undefined}
                max={param.max_value ?? undefined}
                step={param.type === 'float' ? 0.5 : 1}
                value={getValue(param)}
                onChange={(e) => handleChange(param.key, e.target.value)}
                className="w-20 px-3 py-2 border border-gray-200 rounded-lg text-center font-mono text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <div className="flex justify-between mt-2 text-xs text-gray-400">
              <span>Min: {param.min_value ?? 0}</span>
              <span>Max: {param.max_value ?? 100}</span>
            </div>
          </div>
        ))}
      </div>

      <Toast toasts={toasts} removeToast={removeToast} />
    </div>
  );
}
