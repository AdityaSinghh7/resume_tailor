'use client';

import { useEffect } from 'react';
import { useSearchParams } from 'next/navigation';

export default function HomePage() {
  const searchParams = useSearchParams();
  
  useEffect(() => {
    // Extract the access token from the URL query parameters
    const accessToken = searchParams.get('access_token');
    if (accessToken) {
      // Store the access token (e.g., in localStorage)
      localStorage.setItem('github_access_token', accessToken);
      // Optional: Remove the access token from the URL for cleanliness
      window.history.replaceState({}, document.title, '/home');
    }
  }, [searchParams]);

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-4xl mx-auto">
        <div className="bg-white rounded-lg shadow-lg p-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-4">
            Welcome to Resume Tailor!
          </h1>
          <p className="text-gray-600">
            You have successfully logged in. Start creating your tailored resume now!
          </p>
        </div>
      </div>
    </main>
  );
} 