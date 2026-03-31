import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTenantQueryScope } from '@/hooks/useTenantQueryScope';
import * as jobService from '@/services/jobService';
import type { JobSearchRequest } from '@/types/job';

const JOBS_KEY = ['jobs'] as const;

/** Fetch paginated job listings. */
export function useJobs(page = 1, pageSize = 20, status?: string) {
  const scope = useTenantQueryScope();
  return useQuery({
    queryKey: [...scope, ...JOBS_KEY, 'list', page, pageSize, status],
    queryFn: () => jobService.listJobs(page, pageSize, status),
  });
}

/** Fetch a single job by ID. */
export function useJob(jobId: string | undefined) {
  const scope = useTenantQueryScope();
  return useQuery({
    queryKey: [...scope, ...JOBS_KEY, 'detail', jobId],
    queryFn: () => jobService.getJob(jobId!),
    enabled: !!jobId,
  });
}

/** Search for jobs across platforms. */
export function useSearchJobs() {
  const queryClient = useQueryClient();
  const scope = useTenantQueryScope();
  return useMutation({
    mutationFn: (request: JobSearchRequest) => jobService.searchJobs(request),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...scope, ...JOBS_KEY] });
    },
  });
}

/** Analyze a job's match score. */
export function useAnalyzeJob() {
  return useMutation({
    mutationFn: (jobId: string) => jobService.analyzeJob(jobId),
  });
}

/** Delete a job listing. */
export function useDeleteJob() {
  const queryClient = useQueryClient();
  const scope = useTenantQueryScope();
  return useMutation({
    mutationFn: (jobId: string) => jobService.deleteJob(jobId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...scope, ...JOBS_KEY] });
    },
  });
}
