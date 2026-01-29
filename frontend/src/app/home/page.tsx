'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getSupabaseBrowserClient } from '../../lib/supabaseClient';

export default function HomePage() {
  const router = useRouter();
  const [repos, setRepos] = useState<any[]>([]);
  const [selectedRepos, setSelectedRepos] = useState<Set<number>>(new Set());
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [ramble, setRamble] = useState('');
  const [rambleLoading, setRambleLoading] = useState(false);
  const [rambleMessage, setRambleMessage] = useState<string | null>(null);
  const [tokenReady, setTokenReady] = useState(false);

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
            'Authorization': `Bearer ${accessToken}`,
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
    const fetchRepos = async () => {
      if (!tokenReady) return;
      setLoading(true);
      const token = sessionStorage.getItem('jwt_token');
      if (!token) {
        setMessage('No token found. Please log in again.');
        setRepos([]); // Defensive: always set to array
        setLoading(false);
        return;
      }
      try {
        const res = await fetch('http://localhost:8000/api/repositories', {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        });
        if (!res.ok) {
          setRepos([]); // Defensive: always set to array
          setMessage('Error fetching repositories.');
          setLoading(false);
          return;
        }
        const data = await res.json();
        if (Array.isArray(data)) {
          setRepos(data);
          // Set selectedRepos to those with selected = true
          const initiallySelected = new Set<number>(data.filter((repo: any) => repo.selected).map((repo: any) => repo.project_id));
          setSelectedRepos(initiallySelected);
        } else {
          setRepos([]); // Defensive: always set to array
          setMessage('Unexpected response from server.');
        }
      } catch (err) {
        setRepos([]); // Defensive: always set to array
        setMessage('Error fetching repositories.');
      } finally {
        setLoading(false);
      }
    };
    fetchRepos();
  }, [tokenReady]);

  useEffect(() => {
    // Fetch STAR ramble when selectedProjectId changes
    if (selectedProjectId === null) {
      setRamble('');
      return;
    }
    const fetchRamble = async () => {
      setRambleLoading(true);
      const token = sessionStorage.getItem('jwt_token');
      try {
        const res = await fetch(`http://localhost:8000/api/repositories/${selectedProjectId}/star_ramble`, {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        });
        if (res.ok) {
          const data = await res.json();
          setRamble(data.star_ramble || '');
        } else {
          setRamble('');
        }
      } catch {
        setRamble('');
      } finally {
        setRambleLoading(false);
      }
    };
    fetchRamble();
  }, [selectedProjectId]);

  const handleCheckbox = (projectId: number) => {
    setSelectedRepos(prev => {
      const newSet = new Set(prev);
      if (newSet.has(projectId)) {
        newSet.delete(projectId);
      } else {
        newSet.add(projectId);
      }
      return newSet;
    });
  };

  const handleSelectRamble = (projectId: number) => {
    setSelectedProjectId(projectId);
    setRambleMessage(null);
  };

  const handleProcessSelected = async () => {
    setProcessing(true);
    setMessage(null);
    const token = sessionStorage.getItem('jwt_token');
    try {
      const res = await fetch('http://localhost:8000/api/process', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ repo_ids: Array.from(selectedRepos) }),
      });
      const data = await res.json();
      setMessage(data.message || 'Processing started!');
      if (res.ok) {
        // Poll for status
        let pollInterval: NodeJS.Timeout;
        const pollStatus = async () => {
          try {
            const statusRes = await fetch('http://localhost:8000/api/process_status', {
              headers: { 'Authorization': `Bearer ${token}` },
            });
            const statusData = await statusRes.json();
            setMessage(statusData.message || 'Processing...');
            if (statusData.status === 'done') {
              clearInterval(pollInterval);
              setProcessing(false);
              setTimeout(() => {
                router.push('/resume');
              }, 1200);
            } else if (statusData.status === 'error') {
              clearInterval(pollInterval);
              setProcessing(false);
              setMessage('Error: ' + (statusData.message || 'Processing failed.'));
            }
          } catch (e) {
            clearInterval(pollInterval);
            setProcessing(false);
            setMessage('Error polling processing status.');
          }
        };
        pollInterval = setInterval(pollStatus, 900);
        pollStatus(); // initial call
      }
    } catch (err) {
      setMessage('Error processing repositories.');
      setProcessing(false);
    }
  };

  const handleSaveRamble = async () => {
    if (!selectedProjectId) return;
    setRambleMessage(null);
    setRambleLoading(true);
    const token = sessionStorage.getItem('jwt_token');
    try {
      const res = await fetch(`http://localhost:8000/api/repositories/${selectedProjectId}/star_ramble`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ star_ramble: ramble }),
      });
      if (res.ok) {
        setRambleMessage('Ramble saved!');
      } else {
        setRambleMessage('Failed to save ramble.');
      }
    } catch {
      setRambleMessage('Failed to save ramble.');
    } finally {
      setRambleLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-6xl mx-auto">
        <div className="bg-white rounded-lg shadow-lg p-8 flex flex-col md:flex-row gap-8">
          {/* Left: Repo List */}
          <div className="md:w-1/2 w-full">
            <h1 className="text-3xl font-bold text-gray-900 mb-4">
              Welcome to Resume Tailor!
            </h1>
            <p className="text-gray-600 mb-6">
              Select repositories to process and click a project to view/edit its STAR ramble.
            </p>
            {loading ? (
              <div className="text-gray-500">Loading repositories...</div>
            ) : (
              <ul className="divide-y divide-gray-200 mb-6">
                {repos.length === 0 ? (
                  <li className="py-4 text-gray-500">No repositories found.</li>
                ) : (
                  repos.map((repo: any) => (
                    <li key={repo.project_id} className="flex items-center py-3 group cursor-pointer">
                      <input
                        type="checkbox"
                        className="mr-2 h-5 w-5 text-blue-600 rounded"
                        checked={selectedRepos.has(repo.project_id)}
                        onChange={() => handleCheckbox(repo.project_id)}
                        onClick={e => e.stopPropagation()}
                      />
                      <span
                        className={`font-medium flex-1 px-1 rounded transition-colors duration-150 ${selectedProjectId === repo.project_id ? 'font-bold bg-blue-50 text-blue-800' : 'text-gray-800'}`}
                        onClick={() => handleSelectRamble(repo.project_id)}
                      >
                        {repo.github_url}
                      </span>
                      <span className="ml-2">
                        {repo.selected ? (
                          <span className="inline-block px-2 py-0.5 text-xs bg-green-100 text-green-700 rounded-full ml-2">Selected</span>
                        ) : (
                          <span className="inline-block px-2 py-0.5 text-xs bg-gray-200 text-gray-500 rounded-full ml-2">Not Selected</span>
                        )}
                      </span>
                      <span className="ml-auto text-sm text-gray-400">{repo.file_count} files</span>
                    </li>
                  ))
                )}
              </ul>
            )}
            <button
              onClick={handleProcessSelected}
              className="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
              disabled={processing || selectedRepos.size === 0}
            >
              {processing ? 'Processing...' : 'Process Selected'}
            </button>
            {processing && (
              <div className="flex justify-center items-center mt-4">
                <svg className="animate-spin h-8 w-8 text-blue-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"></path>
                </svg>
                <span className="ml-3 text-blue-700">Processing repositories, please wait...</span>
              </div>
            )}
            {message && (
              <div className="mt-4 text-blue-700 bg-blue-100 p-2 rounded">{message}</div>
            )}
          </div>
          {/* Right: STAR Ramble */}
          <div className="md:w-1/2 w-full">
            {selectedProjectId ? (
              <>
                <h2 className="text-xl font-semibold text-gray-800 mb-2">STAR Ramble for Selected Project</h2>
                <p className="text-gray-500 mb-2 text-sm">
                  Write or edit your STAR format (Situation, Task, Action, Result) ramble for this project.
                </p>
                <textarea
                  className="w-full min-h-[220px] border border-gray-300 rounded p-3 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
                  placeholder={`Situation: What was the context?\nTask: What was your responsibility?\nAction: What did you do?\nResult: What was the outcome?`}
                  value={ramble}
                  onChange={e => setRamble(e.target.value)}
                  disabled={rambleLoading}
                />
                <button
                  onClick={handleSaveRamble}
                  className="mt-3 px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
                  disabled={rambleLoading}
                >
                  {rambleLoading ? 'Saving...' : 'Save Ramble'}
                </button>
                {rambleMessage && (
                  <div className="mt-2 text-green-700 bg-green-100 p-2 rounded">{rambleMessage}</div>
                )}
                {rambleLoading && <div className="text-gray-400 mt-2">Loading ramble...</div>}
              </>
            ) : (
              <div className="text-gray-400 italic mt-12">Select a project to view or edit its STAR ramble.</div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
} 
