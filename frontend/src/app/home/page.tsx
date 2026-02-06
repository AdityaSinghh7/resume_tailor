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
  const readyRepos = useMemo(() => repos.filter((repo) => repo.embeddings_ready).length, [repos]);
  const processingRepos = repos.length - readyRepos;

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
    <main
      className="min-h-screen bg-slate-50 text-slate-900"
      style={{ fontFamily: '"Space Grotesk", "Avenir Next", "Segoe UI", sans-serif' }}
    >
      <div className="flex min-h-screen w-full overflow-hidden bg-white">
        <aside className="w-72 flex-shrink-0 border-r border-indigo-950/10 bg-indigo-950 p-5 text-indigo-100">
          <div className="mb-6 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-700 text-lg font-bold">
              RT
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-indigo-300">Resume Tailor</p>
              <h1 className="text-lg font-semibold">Studio</h1>
            </div>
          </div>

          <div className="mb-4 rounded-xl bg-indigo-900/70 p-3">
            <p className="text-xs uppercase tracking-wider text-indigo-300">Workspace</p>
            <p className="mt-1 text-sm font-semibold">GitHub Resume Builder</p>
            <p className="mt-1 text-xs text-indigo-300">{repos.length} repos · {totalFiles} files</p>
          </div>

          <details className="group rounded-xl border border-indigo-900 bg-indigo-900/70">
            <summary className="cursor-pointer list-none px-3 py-2 text-xs font-semibold uppercase tracking-wider text-indigo-200">
              <span className="flex items-center justify-between">
                <span>Repositories</span>
                <span className="text-xs transition-transform duration-200 group-open:rotate-180">▾</span>
              </span>
            </summary>
            <div className="space-y-2 overflow-y-auto px-3 py-2" style={{ maxHeight: '66vh' }}>
              {loadingRepos ? (
                <p className="text-sm text-indigo-300">Loading repositories...</p>
              ) : repos.length === 0 ? (
                <p className="text-sm text-indigo-300">No repositories found yet.</p>
              ) : (
                repos.map((repo) => (
                  <details key={repo.project_id} className="rounded-lg border border-indigo-900 bg-indigo-900/60">
                    <summary className="cursor-pointer list-none px-3 py-2">
                      <p className="truncate text-sm font-semibold text-indigo-100">{repo.full_name || repo.github_url}</p>
                      <div className="mt-1 flex items-center justify-between text-[11px]">
                        <span className="text-indigo-300">{repo.file_count} files</span>
                        <span className={`rounded-full px-2 py-0.5 ${repo.embeddings_ready ? 'bg-emerald-200 text-emerald-900' : 'bg-amber-200 text-amber-900'}`}>
                          {repo.embeddings_ready ? 'Ready' : 'Processing'}
                        </span>
                      </div>
                    </summary>
                    <div className="max-h-44 overflow-y-auto border-t border-indigo-800 px-3 py-2">
                      {repo.files.map((file) => (
                        <p key={file.id} className="truncate rounded bg-indigo-950/70 px-2 py-1 text-xs text-indigo-200">
                          {file.file_path}
                        </p>
                      ))}
                    </div>
                  </details>
                ))
              )}
            </div>
          </details>
        </aside>

        <section className="flex-1 overflow-y-auto bg-slate-50 p-4 md:p-6">
          <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold uppercase tracking-wider text-indigo-600">Dashboard</p>
              <h2 className="text-2xl font-bold text-slate-900">GitHub to Resume Assistant</h2>
            </div>
            <div className="rounded-full bg-white px-4 py-2 text-xs font-semibold text-slate-600 shadow-sm">
              {repos.length} repos • {totalFiles} files
            </div>
          </header>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-xl border-t-4 border-violet-500 bg-white p-4 shadow-sm">
              <p className="text-xs uppercase tracking-wider text-slate-500">Repos Connected</p>
              <p className="mt-2 text-3xl font-bold">{repos.length}</p>
            </div>
            <div className="rounded-xl border-t-4 border-amber-500 bg-white p-4 shadow-sm">
              <p className="text-xs uppercase tracking-wider text-slate-500">Files Indexed</p>
              <p className="mt-2 text-3xl font-bold">{totalFiles}</p>
            </div>
            <div className="rounded-xl border-t-4 border-emerald-500 bg-white p-4 shadow-sm">
              <p className="text-xs uppercase tracking-wider text-slate-500">Ready Repos</p>
              <p className="mt-2 text-3xl font-bold">{readyRepos}</p>
            </div>
            <div className="rounded-xl border-t-4 border-sky-500 bg-white p-4 shadow-sm">
              <p className="text-xs uppercase tracking-wider text-slate-500">Processing</p>
              <p className="mt-2 text-3xl font-bold">{processingRepos}</p>
            </div>
          </div>

          <div className="mt-5 rounded-2xl bg-white p-5 shadow-sm">
            <h3 className="text-xl font-bold text-slate-900">Job Description Analyzer</h3>
            <p className="mt-1 text-sm text-slate-600">Paste a JD and generate targeted resume bullets from your best-matching projects.</p>

            <form onSubmit={handleSubmit} className="mt-4 space-y-4">
              <textarea
                className="min-h-[190px] w-full rounded-xl border border-slate-300 bg-slate-50 p-4 text-sm outline-none focus:border-violet-500"
                placeholder="Paste job description here..."
                value={jobDescription}
                onChange={(e) => setJobDescription(e.target.value)}
                required
              />
              <div className="flex flex-wrap items-center gap-3">
                <label className="text-sm font-medium text-slate-700">Top projects</label>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={numProjects}
                  onChange={(e) => setNumProjects(Number(e.target.value))}
                  className="w-20 rounded-md border border-slate-300 px-2 py-1 text-sm"
                />
                <button
                  type="submit"
                  disabled={loadingResults}
                  className="rounded-md bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-50"
                >
                  {loadingResults ? 'Generating...' : 'Generate Bullets'}
                </button>
              </div>
            </form>

            {message && <div className="mt-4 rounded bg-sky-100 p-2 text-sm text-sky-800">{message}</div>}
            {error && <div className="mt-4 rounded bg-rose-100 p-2 text-sm text-rose-700">{error}</div>}
          </div>

          <div className="mt-5 space-y-4">
            {results.map((entry, idx) => (
              <article key={`${entry.github_url}-${idx}`} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <h3 className="text-lg font-semibold text-slate-900">{entry.title}</h3>
                  <a href={entry.github_url} target="_blank" rel="noopener noreferrer" className="text-sm text-violet-700 hover:underline">
                    GitHub
                  </a>
                </div>
                {typeof entry.alignment_score !== 'undefined' && (
                  <p className="mb-2 text-xs text-slate-500">Alignment score: {entry.alignment_score.toFixed(3)}</p>
                )}
                <ul className="list-disc space-y-1 pl-5 text-sm text-slate-800">
                  {entry.bullets.map((bullet, i) => (
                    <li key={i}>{bullet}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
