import { useQuery } from '@tanstack/react-query';

import { useTenantQueryScope } from '@/hooks/useTenantQueryScope';
import * as candidateService from '@/services/candidateService';

const CANDIDATES_KEY = ['candidates'] as const;

export function useCandidates() {
  const scope = useTenantQueryScope();
  return useQuery({
    queryKey: [...scope, ...CANDIDATES_KEY, 'list'],
    queryFn: () => candidateService.listCandidates(),
  });
}

export function useCandidate(candidateId: string | undefined) {
  const scope = useTenantQueryScope();
  return useQuery({
    queryKey: [...scope, ...CANDIDATES_KEY, 'detail', candidateId],
    queryFn: () => candidateService.getCandidate(candidateId!),
    enabled: !!candidateId,
  });
}
