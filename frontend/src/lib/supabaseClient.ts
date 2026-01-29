import type { SupabaseClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? '';
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? '';

if (!supabaseUrl || !supabaseAnonKey) {
  // eslint-disable-next-line no-console
  console.warn('Supabase env vars are missing. Check NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.');
}

let browserClient: SupabaseClient | null = null;
let supabaseModulePromise: Promise<typeof import('@supabase/supabase-js')> | null = null;

export const getSupabaseBrowserClient = async () => {
  if (typeof window === 'undefined') {
    throw new Error('Supabase client is only available in the browser.');
  }
  if (browserClient) {
    return browserClient;
  }
  if (!supabaseModulePromise) {
    supabaseModulePromise = import('@supabase/supabase-js');
  }
  const { createClient } = await supabaseModulePromise;
  browserClient = createClient(supabaseUrl, supabaseAnonKey, {
    auth: {
      storage: window.localStorage,
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
  });
  return browserClient;
};
