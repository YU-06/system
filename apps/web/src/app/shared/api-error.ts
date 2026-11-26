import { HttpErrorResponse } from '@angular/common/http';

export function correlationIdFrom(error: unknown): string | null {
  return error instanceof HttpErrorResponse ? error.headers.get('X-Correlation-Id') : null;
}

export function statusFrom(error: unknown): number | null {
  return error instanceof HttpErrorResponse ? error.status : null;
}
