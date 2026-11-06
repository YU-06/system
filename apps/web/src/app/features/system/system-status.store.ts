import { HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { finalize } from 'rxjs';
import { SystemService, SystemStatusDto } from '../../proxy/system';

export type SystemState =
  | { kind: 'loading' }
  | { kind: 'success'; data: SystemStatusDto }
  | { kind: 'empty' }
  | { kind: 'error'; correlationId: string | null };

@Injectable({ providedIn: 'root' })
export class SystemStatusStore {
  private readonly api = inject(SystemService);
  private pending = false;
  readonly state = signal<SystemState>({ kind: 'loading' });

  constructor() {
    this.refresh();
  }

  refresh(): void {
    if (this.pending) return;
    this.pending = true;
    this.state.set({ kind: 'loading' });
    this.api
      .get({ skipHandleError: true })
      .pipe(finalize(() => (this.pending = false)))
      .subscribe({
        next: (data) =>
          this.state.set(data?.service ? { kind: 'success', data } : { kind: 'empty' }),
        error: (error: unknown) =>
          this.state.set({
            kind: 'error',
            correlationId:
              error instanceof HttpErrorResponse ? error.headers.get('X-Correlation-Id') : null,
          }),
      });
  }
}
