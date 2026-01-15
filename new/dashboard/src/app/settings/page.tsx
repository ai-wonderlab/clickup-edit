'use client';

import { useEffect, useState } from 'react';
import { supabase, Parameter } from '@/lib/supabase';
import { Save, RotateCcw, Info } from 'lucide-react';
import Toast, { useToast } from '@/components/Toast';

// All 8 configurable parameters
const DEFAULT_PARAMETERS: Omit<Parameter, 'id'>[] = [
  {
    key: 'VALIDATION_PASS_THRESHOLD',
    value: '8',
    type: 'int',
    min_value: 1,
    max_value: 10,
    updated_at: new Date().toISOString(),
  },
  {
    key: 'MAX_ITERATIONS',
    value: '3',
    type: 'int',
    min_value: 1,
    max_value: 10,
    updated_at: new Date().toISOString(),
  },
  {
    key: 'MAX_STEP_ATTEMPTS',
    value: '2',
    type: 'int',
    min_value: 1,
    max_value: 5,
    updated_at: new Date().toISOString(),
  },
  {
    key: 'TIMEOUT_OPENROUTER_SECONDS',
    value: '120',
    type: 'float',
    min_value: 30,
    max_value: 600,
    updated_at: new Date().toISOString(),
  },
  {
    key: 'TIMEOUT_WAVESPEED_SECONDS',
    value: '300',
    type: 'float',
    min_value: 60,
    max_value: 900,
    updated_at: new Date().toISOString(),
  },
  {
    key: 'RATE_LIMIT_ENHANCEMENT',
    value: '5',
    type: 'int',
    min_value: 1,
    max_value: 20,
    updated_at: new Date().toISOString(),
  },
  {
    key: 'RATE_LIMIT_VALIDATION',
    value: '3',
    type: 'int',
    min_value: 1,
    max_value: 10,
    updated_at: new Date().toISOString(),
  },
  {
    key: 'VALIDATION_DELAY_SECONDS',
    value: '2',
    type: 'float',
    min_value: 0,
    max_value: 10,
    updated_at: new Date().toISOString(),
  },
];

const PARAMETER_DESCRIPTIONS: Record<string, string> = {
  VALIDATION_PASS_THRESHOLD: 'Minimum score (1-10) to pass validation',
  MAX_ITERATIONS: 'Maximum refinement iterations before fallback',
  MAX_STEP_ATTEMPTS: 'Retry attempts per sequential step',
  TIMEOUT_OPENROUTER_SECONDS: 'Claude API timeout in seconds',
  TIMEOUT_WAVESPEED_SECONDS: 'WaveSpeed API timeout in seconds',
  RATE_LIMIT_ENHANCEMENT: 'Max concurrent enhancement calls',
  RATE_LIMIT_VALIDATION: 'Max concurrent validation calls',
  VALIDATION_DELAY_SECONDS: 'Delay between validation calls',
};

export default function Settings() {
  const [parameters, setParameters] = useState<Parameter[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [changes, setChanges] = useState<Record<string, string>>({});
  const { toasts, addToast, removeToast } = useToast();

  useEffect(() => {
    fetchParameters();
  }, []);

  const fetchParameters = async () => {
    if (!supabase) {
      // Use defaults if no Supabase
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

      if (error) throw error;

      // Merge with defaults to ensure all 8 are present
      const merged = DEFAULT_PARAMETERS.map((def, i) => {
        const existing = data?.find((d) => d.key === def.key);
        return existing || { ...def, id: `default-${i}` };
      });

      setParameters(merged);
      addToast('success', `Loaded ${merged.length} parameters`);
    } catch (err) {
      addToast('error', 'Failed to load parameters');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (key: string, value: string) => {
    setChanges((prev) => ({ ...prev, [key]: value }));
  };

  const getValue = (param: Parameter) => {
    return changes[param.key] ?? param.value;
  };

  const handleSaveAll = async () => {
    if (!supabase || Object.keys(changes).length === 0) {
      addToast('info', 'No changes to save');
      return;
    }

    setSaving(true);
    try {
      for (const [key, value] of Object.entries(changes)) {
        const param = parameters.find((p) => p.key === key);
        if (param && !param.id.startsWith('default-')) {
          const { error } = await supabase
            .from('parameters')
            .update({ value, updated_at: new Date().toISOString() })
            .eq('id', param.id);

          if (error) throw error;
        } else {
          // Insert new parameter
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

      addToast('success', `Saved ${Object.keys(changes).length} parameter(s)`);
      setChanges({});
      fetchParameters();
    } catch (err) {
      addToast('error', 'Failed to save parameters');
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
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
          <p className="text-gray-600 mt-1">Configure pipeline parameters</p>
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
            className={`p-4 border rounded-lg transition-all ${
              changes[param.key] !== undefined
                ? 'border-blue-300 bg-blue-50'
                : 'border-gray-200 bg-white'
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