import type { SessionRole } from '@/types/session';

const ROLE_ORDER: SessionRole[] = ['read_only', 'operator', 'admin', 'owner'];

export function canAccess(role: SessionRole | null, minimum: SessionRole): boolean {
  if (!role) {
    return false;
  }
  return ROLE_ORDER.indexOf(role) >= ROLE_ORDER.indexOf(minimum);
}

export function hasAnyRole(role: SessionRole | null, allowed?: SessionRole[]): boolean {
  if (!allowed || allowed.length === 0) {
    return true;
  }
  if (!role) {
    return false;
  }
  return allowed.includes(role);
}
