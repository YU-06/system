import { DestroyRef, Injectable, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  ExperimentRunService,
  type ExperimentRunDto,
  type ExperimentRunListInput,
} from '../../proxy/research';
import { correlationIdFrom } from '../../shared/api-error';

export type ExperimentState =
  | { kind: 'loading' }
  | { kind: 'success'; experiments: ExperimentRunDto[]; totalCount: number }
  | { kind: 'empty' }
  | { kind: 'error'; correlationId: string | null };

@Injectable()
export class ExperimentStore {
  private readonly destroyRef = inject(DestroyRef);
  private readonly api = inject(ExperimentRunService);
  readonly state = signal<ExperimentState>({ kind: 'loading' });
  readonly pageIndex = signal(0);
  private currentInput: ExperimentRunListInput = { skipCount: 0, maxResultCount: 20 };

  load(input: ExperimentRunListInput = this.currentInput): void {
    this.currentInput = input;
    this.pageIndex.set(Math.floor((input.skipCount ?? 0) / 20));
    this.state.set({ kind: 'loading' });
    this.api
      .getList(input, undefined, { skipHandleError: true })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          const experiments = result.items ?? [];
          this.state.set(
            experiments.length
              ? {
                  kind: 'success',
                  experiments,
                  totalCount: result.totalCount ?? experiments.length,
                }
              : { kind: 'empty' },
          );
        },
        error: (error: unknown) =>
          this.state.set({ kind: 'error', correlationId: correlationIdFrom(error) }),
      });
  }

  changePage(delta: number): void {
    const state = this.state();
    if (state.kind !== 'success') return;
    const nextPage = this.pageIndex() + delta;
    if (nextPage < 0 || nextPage * 20 >= state.totalCount) return;
    this.load({ ...this.currentInput, skipCount: nextPage * 20 });
  }
}
