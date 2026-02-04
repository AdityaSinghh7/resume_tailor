'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getSupabaseBrowserClient } from '../../lib/supabaseClient';

type FileItem = {
  id: number;
  file_path: string;
  language: string | null;
  path_bucket: string | null;
};

type RepoItem = {
  project_id: number;
  github_url: string;
  full_name: string | null;
  selected: boolean;
  embeddings_ready: boolean;
  file_count: number;
  files: FileItem[];
};

type ResumeEntry = {
  title: string;
  github_url: string;
  bullets: string[];
  technologies: string[];
  alignment_score?: number;
};

export default function HomePage() {
  const router = useRouter();
  const [repos, setRepos] = useState<RepoItem[]>([]);
  const [tokenReady, setTokenReady] = useState(false);
  const [loadingRepos, setLoadingRepos] = useState(true);
  const [jobDescription, setJobDescription] = useState('');
  const [numProjects, setNumProjects] = useState(3);
  const [results, setResults] = useState<ResumeEntry[]>([]);
  const [loadingResults, setLoadingResults] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const initSession = async () => {
      const supabase = await getSupabaseBrowserClient();
      const { data } = await supabase.auth.getSession();
      const session = data.session;
      if (!session) {
        router.push('/');
        return;
      }
      const accessToken = session.access_token;
      sessionStorage.setItem('jwt_token', accessToken);
      try {
        const providerToken = session.provider_token;
        if (!providerToken) {
          setMessage('Missing GitHub provider token. Please sign in again.');
          setTokenReady(true);
          return;
        }
        const res = await fetch('http://localhost:8000/auth/supabase/session', {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${accessToken}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ provider_token: providerToken }),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          setMessage(data.detail || 'Failed to initialize session.');
        }
      } catch {
        setMessage('Failed to initialize session.');
      } finally {
        setTokenReady(true);
      }
    };
    initSession();
  }, [router]);

  useEffect(() => {
    if (!tokenReady) return;

    let cancelled = false;
    let pollTimer: NodeJS.Timeout | null = null;

    const fetchRepoNames = async (token: string) => {
      await fetch('http://localhost:8000/api/github_repos', {
        headers: { Authorization: `Bearer ${token}` },
      });
    };

    const fetchIngestedFiles = async (token: string) => {
      try {
        const res = await fetch('http://localhost:8000/api/ingested_files', {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled && Array.isArray(data)) {
          setRepos(data);
        }
      } finally {
        if (!cancelled) setLoadingRepos(false);
      }
    };

    const run = async () => {
      const token = sessionStorage.getItem('jwt_token');
      if (!token) {
        setError('No token found. Please log in again.');
        setLoadingRepos(false);
        return;
      }
      await fetchRepoNames(token);
      await fetchIngestedFiles(token);
      pollTimer = setInterval(() => {
        fetchIngestedFiles(token);
      }, 4000);
    };

    run();

    return () => {
      cancelled = true;
      if (pollTimer) clearInterval(pollTimer);
    };
  }, [tokenReady]);

  const totalFiles = useMemo(() => repos.reduce((acc, repo) => acc + repo.file_count, 0), [repos]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoadingResults(true);
    setError(null);
    setResults([]);

    const token = sessionStorage.getItem('jwt_token');
    if (!token) {
      setError('No active session. Please sign in again.');
      setLoadingResults(false);
      return;
    }

    try {
      const response = await fetch('http://localhost:8000/api/rag_resume', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          job_description: jobDescription,
          n_projects: Number(numProjects),
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to fetch recommendations');
      }

      const data = await response.json();
      setResults(data.entries || []);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch recommendations.');
    } finally {
      setLoadingResults(false);
    }
  };

  return (
    <main className="min-h-screen bg-stone-100 text-stone-900">
      <div className="mx-auto grid max-w-7xl grid-cols-1 gap-6 p-6 md:grid-cols-[360px_1fr]">
        <aside className="rounded-2xl border border-stone-200 bg-white p-4 shadow-sm">
          <h1 className="text-2xl font-bold">Ingested Files</h1>
          <p className="mt-1 text-sm text-stone-600">{repos.length} repos · {totalFiles} files</p>
          {loadingRepos ? (
            <div className="mt-4 text-sm text-stone-500">Loading repositories...</div>
          ) : repos.length === 0 ? (
            <div className="mt-4 text-sm text-stone-500">No repositories found yet.</div>
          ) : (
            <div className="mt-4 space-y-3 overflow-y-auto pr-1" style={{ maxHeight: '78vh' }}>
              {repos.map((repo) => (
                <details key={repo.project_id} className="rounded-lg border border-stone-200 bg-stone-50">
                  <summary className="cursor-pointer list-none px-3 py-2">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-semibold text-stone-900">{repo.full_name || repo.github_url}</p>
                        <p className="text-xs text-stone-600">{repo.file_count} files indexed</p>
                      </div>
                      <span className={`rounded-full px-2 py-0.5 text-xs ${repo.embeddings_ready ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
                        {repo.embeddings_ready ? 'Ready' : 'Processing'}
                      </span>
                    </div>
                  </summary>
                  <div className="max-h-64 overflow-y-auto border-t border-stone-200 bg-white px-3 py-2 text-xs">
                    {repo.files.length === 0 ? (
                      <p className="text-stone-500">Files are still being ingested...</p>
                    ) : (
                      repo.files.map((file) => (
                        <div key={file.id} className="mb-1 rounded border border-stone-100 bg-stone-50 px-2 py-1">
                          <p className="truncate text-stone-800">{file.file_path}</p>
                          <p className="text-[11px] text-stone-500">{file.language || 'unknown'} · {file.path_bucket || 'other'}</p>
                        </div>
                      ))
                    )}
                  </div>
                </details>
              ))}
            </div>
          )}
        </aside>

        <section className="rounded-2xl border border-stone-200 bg-white p-6 shadow-sm">
          <h2 className="text-2xl font-bold">Job Match Recommendations</h2>
          <p className="mt-1 text-sm text-stone-600">Paste a job description to get recommended projects and bullet points.</p>

          <form onSubmit={handleSubmit} className="mt-5 space-y-4">
            <textarea
              className="min-h-[180px] w-full rounded-xl border border-stone-300 bg-stone-50 p-4 text-sm outline-none ring-0 focus:border-blue-500"
              placeholder="Paste job description here..."
              value={jobDescription}
              onChange={(e) => setJobDescription(e.target.value)}
              required
            />
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-stone-700">Top projects:</label>
              <input
                type="number"
                min={1}
                max={10}
                value={numProjects}
                onChange={(e) => setNumProjects(Number(e.target.value))}
                className="w-16 rounded-md border border-stone-300 px-2 py-1 text-sm"
              />
              <button
                type="submit"
                disabled={loadingResults}
                className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {loadingResults ? 'Finding Matches...' : 'Find Matches'}
              </button>
            </div>
          </form>

          {message && <div className="mt-4 rounded bg-blue-100 p-2 text-sm text-blue-800">{message}</div>}
          {error && <div className="mt-4 rounded bg-red-100 p-2 text-sm text-red-700">{error}</div>}

          <div className="mt-6 space-y-4">
            {results.map((entry, idx) => (
              <article key={`${entry.github_url}-${idx}`} className="rounded-xl border border-stone-200 bg-stone-50 p-4">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <h3 className="text-lg font-semibold text-stone-900">{entry.title}</h3>
                  <a href={entry.github_url} target="_blank" rel="noopener noreferrer" className="text-sm text-blue-700 hover:underline">
                    GitHub
                  </a>
                </div>
                {typeof entry.alignment_score !== 'undefined' && (
                  <p className="mb-2 text-xs text-stone-500">Alignment score: {entry.alignment_score.toFixed(3)}</p>
                )}
                <ul className="list-disc space-y-1 pl-5 text-sm text-stone-800">
                  {entry.bullets.map((bullet, i) => (
                    <li key={i}>{bullet}</li>
                  ))}
                </ul>
                <p className="mt-3 text-xs text-stone-500">Technologies: {entry.technologies.join(', ')}</p>
              </article>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
