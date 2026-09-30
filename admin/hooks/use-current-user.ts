import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { SessionUser } from '@/lib/session';

export function useCurrentUser() {
  return useQuery({
    queryKey: ['auth', 'me'],
    queryFn: () => apiFetch<SessionUser>('auth/me'),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}
