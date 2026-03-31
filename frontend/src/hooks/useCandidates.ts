import { useQuery } from '@tanstack/react-query';

import * as candidateService from '@/services/candidateService';

const CANDIDATES_KEY = ['candidates'] as const;

export function useCandidates() {
  return useQuery({
    queryKey: [...CANDIDATES_KEY, 'list'],
    queryFn: () => candidateService.listCandidates(),
  });
}

export function useCandidate(candidateId: string | undefined) {
  return useQuery({
    queryKey: [...CANDIDATES_KEY, 'detail', candidateId],
    queryFn: () => candidateService.getCandidate(candidateId!),
    enabled: !!candidateId,
  });
}
