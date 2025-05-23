"use client";

import { useState } from "react";

export default function ResumeBuilderPage() {
  const [jobDescription, setJobDescription] = useState("");
  const [numProjects, setNumProjects] = useState(3);
  const [output, setOutput] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Placeholder for submit handler
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setOutput([]);
    // Debug log
    console.log({
      job_description: jobDescription,
      n_projects: numProjects,
      typeofNumProjects: typeof numProjects
    });
    const token = sessionStorage.getItem('jwt_token');
    try {
      const response = await fetch("http://localhost:8000/api/rag_resume", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": token ? `Bearer ${token}` : ""
        },
        body: JSON.stringify({
          job_description: jobDescription,
          n_projects: Number(numProjects) // Ensure it's a number
        })
      });
      if (!response.ok) {
        throw new Error("Failed to generate resume");
      }
      const data = await response.json();
      setOutput(data.entries);
    } catch (err: any) {
      setError(err.message || "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-3xl mx-auto bg-white rounded-lg shadow-lg p-8">
        <h1 className="text-2xl font-bold mb-4 text-gray-900">Resume Builder</h1>
        <form onSubmit={handleSubmit} className="mb-8">
          <label className="block mb-2 font-medium text-gray-700">Job Description</label>
          <textarea
            className="w-full min-h-[120px] border border-gray-300 rounded p-3 mb-4 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
            placeholder="Paste the job description here..."
            value={jobDescription}
            onChange={e => setJobDescription(e.target.value)}
            required
          />
          <div className="flex items-center gap-4 mb-4">
            <label className="font-medium text-gray-700">Number of Projects to Include:</label>
            <input
              type="number"
              min={1}
              max={10}
              value={numProjects}
              onChange={e => setNumProjects(Number(e.target.value))}
              className="w-16 border border-gray-300 rounded px-2 py-1 text-gray-800"
            />
          </div>
          <button
            type="submit"
            className="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            disabled={loading}
          >
            {loading ? "Generating..." : "Generate Resume"}
          </button>
        </form>
        {error && <div className="text-red-600 mb-4">{error}</div>}
        <section>
          {output.length > 0 && (
            <div>
              <h2 className="text-xl font-semibold mb-4 text-gray-800">Resume Entries</h2>
              <ul className="space-y-6">
                {output.map((entry, idx) => (
                  <li key={idx} className="border border-gray-200 rounded-lg p-5 bg-gray-50">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-lg font-bold text-blue-900">{entry.title}</span>
                      <a href={entry.github_url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline text-sm">GitHub</a>
                    </div>
                    {typeof entry.alignment_score !== 'undefined' && (
                      <div className="text-xs text-gray-500 mb-1">Alignment Score: {entry.alignment_score.toFixed(3)}</div>
                    )}
                    <ul className="list-disc pl-6 text-gray-800 mb-2">
                      {entry.bullets.map((b: string, i: number) => (
                        <li key={i}>{b}</li>
                      ))}
                    </ul>
                    <div className="text-xs text-gray-500">Technologies: {entry.technologies.join(", ")}</div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      </div>
    </main>
  );
} 