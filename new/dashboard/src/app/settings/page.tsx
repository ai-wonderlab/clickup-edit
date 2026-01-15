'use client';

import { useEffect, useState } from 'react';
import { supabase, Parameter } from '@/lib/supabase';
import { Save } from 'lucide-react';

export default function Settings() {
  const [parameters, setParameters] = useState<Parameter[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchParameters();
  }, []);

  async function fetchParameters() {
    if (!supabase) {
      setLoading(false);
      return;
    }
    
    const { data } = await supabase
      .from('parameters')
      .select('*')
      .order('key');

    if (data) setParameters(data);
    setLoading(false);
  }

  async function updateParameter(key: string, value: string) {
    setParameters(prev =>
      prev.map(p => p.key === key ? { ...p, value } : p)
    );
  }

  async function saveAll() {
    if (!supabase) return;
    
    setSaving(true);
    
    for (const param of parameters) {
      await supabase
        .from('parameters')
        .update({ value: param.value, updated_at: new Date().toISOString() })
        .eq('key', param.key);
    }
    
    setSaving(false);
    alert('Settings saved!');
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Settings</h1>
          <p className="text-gray-500 mt-1">Configure pipeline parameters</p>
        </div>
        <button
          onClick={saveAll}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          <Save size={16} />
          {saving ? 'Saving...' : 'Save All'}
        </button>
      </div>

      {loading ? (
        <div className="text-center py-8">Loading...</div>
      ) : parameters.length === 0 ? (
        <div className="text-center py-12 text-gray-500 bg-white rounded-xl border">
          No parameters in database. Add parameters via SQL.
        </div>
      ) : (
        <div className="grid gap-6">
          {parameters.map((param) => (
            <div
              key={param.id}
              className="p-6 bg-white rounded-xl border"
            >
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="font-bold text-gray-900">{param.key}</h3>
                  <span className="text-sm text-gray-500">Type: {param.type}</span>
                </div>
                <input
                  type={param.type === 'int' ? 'number' : 'text'}
                  value={param.value}
                  onChange={(e) => updateParameter(param.key, e.target.value)}
                  min={param.min_value ?? undefined}
                  max={param.max_value ?? undefined}
                  className="w-32 px-3 py-2 border rounded-lg text-center font-mono"
                />
              </div>
              {param.min_value !== null && param.max_value !== null && (
                <input
                  type="range"
                  value={param.value}
                  onChange={(e) => updateParameter(param.key, e.target.value)}
                  min={param.min_value}
                  max={param.max_value}
                  className="w-full"
                />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

