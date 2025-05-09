'use client';

import { useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { useState } from 'react';

export default function HomePage() {
  const searchParams = useSearchParams();
  const [meResult, setMeResult] = useState<string | null>(null);
  
  useEffect(() => {
    // Extract the access token from the URL query parameters
    const accessToken = searchParams.get('access_token');
    if (accessToken) {
      // Store the access token (e.g., in localStorage)
      sessionStorage.setItem('jwt_token', accessToken);
      // Optional: Remove the access token from the URL for cleanliness
      window.history.replaceState({}, document.title, '/home');
    }
  }, [searchParams]);

  const handleCheckMe = async () => {
    const token = sessionStorage.getItem('jwt_token');
    if (!token) {
      setMeResult('No token found.');
      return;
    }
    try {
      const res = await fetch('http://localhost:8000/auth/github/me', {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      const data = await res.json();
      setMeResult(JSON.stringify(data, null, 2));
    } catch (err) {
      setMeResult('Error fetching /me');
    }
  };

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-4xl mx-auto">
        <div className="bg-white rounded-lg shadow-lg p-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-4">
            Welcome to Resume Tailor!
          </h1>
          <p className="text-gray-600 mb-4">
            You have successfully logged in. Start creating your tailored resume now!
          </p>
          <button
            onClick={handleCheckMe}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Check /me (JWT Protected)
          </button>
          {meResult && (
            <pre className="mt-4 bg-gray-100 p-2 rounded text-sm text-gray-800">{meResult}</pre>
          )}
        </div>
      </div>
    </main>
  );
} 