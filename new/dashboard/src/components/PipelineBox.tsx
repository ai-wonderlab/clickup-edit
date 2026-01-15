import Link from 'next/link';

interface PipelineBoxProps {
  name: string;
  icon: string;
  description: string;
  prompts: string[];
  href: string;
}

export default function PipelineBox({ name, icon, description, prompts, href }: PipelineBoxProps) {
  return (
    <Link
      href={href}
      className="block p-6 bg-white rounded-xl border-2 border-gray-200 hover:border-blue-400 hover:shadow-lg transition-all"
    >
      <div className="text-4xl mb-3">{icon}</div>
      <h3 className="text-lg font-bold text-gray-900 mb-1">{name}</h3>
      <p className="text-sm text-gray-500 mb-3">{description}</p>
      <div className="text-xs text-gray-400">
        {prompts.length} prompts: {prompts.join(', ')}
      </div>
    </Link>
  );
}

