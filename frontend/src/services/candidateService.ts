import api from './api';
import type { Candidate, CandidateListResponse, CandidateSettings } from '@/types/candidate';

export async function listCandidates(): Promise<CandidateListResponse> {
  const { data } = await api.get<CandidateListResponse>('/candidates/');
  return data;
}

export async function getCandidate(candidateId: string): Promise<Candidate> {
  const { data } = await api.get<Candidate>(`/candidates/${candidateId}`);
  return data;
}

export async function getCandidateSettings(candidateId: string): Promise<CandidateSettings> {
  const { data } = await api.get<CandidateSettings>(`/candidates/${candidateId}/settings`);
  return data;
}
