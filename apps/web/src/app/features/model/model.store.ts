import { DestroyRef, Injectable, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  ModelVersionService,
  type ModelVersionDto,
  type ModelVersionListInput,
} from '../../proxy/research';
import { correlationIdFrom } from '../../shared/api-error';

export type ModelState =
  | { kind: 'loading' }
  | { kind: 'success'; models: ModelVersionDto[]; totalCount: number }
  | { kind: 'empty' }
  | { kind: 'error'; correlationId: string | null };

@Injectable()
export class ModelStore {
  private readonly destroyRef = inject(DestroyRef);
  private readonly api = inject(ModelVersionService);
  readonly state = signal<ModelState>({ kind: 'loading' });
  readonly actionError = signal<string | null>(null);
  readonly pageIndex = signal(0);
  private currentInput: ModelVersionListInput = { skipCount: 0, maxResultCount: 20 };

  load(input: ModelVersionListInput = this.currentInput): void {
    this.currentInput = input;
    this.pageIndex.set(Math.floor((input.skipCount ?? 0) / 20));
    this.state.set({ kind: 'loading' });
    this.api
      .getList(input, undefined, { skipHandleError: true })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          const models = result.items ?? [];
          this.state.set(
            models.length
              ? { kind: 'success', models, totalCount: result.totalCount ?? models.length }
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

  toggleActive(model: ModelVersionDto): void {
    if (!model.id || !model.concurrencyStamp) return;
    this.actionError.set(null);
    const active = !model.isActive;
    this.api
      .setState(
        model.id,
        {
          concurrencyStamp: model.concurrencyStamp,
          isActive: active,
          isDefault: Boolean(model.isDefault && active),
        },
        undefined,
        { skipHandleError: true },
      )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => this.load(),
        error: (error: unknown) => this.actionError.set(correlationIdFrom(error) ?? 'request'),
      });
  }

  toggleDefault(model: ModelVersionDto): void {
    if (!model.id || !model.concurrencyStamp || !model.isActive) return;
    this.actionError.set(null);
    this.api
      .setState(
        model.id,
        {
          concurrencyStamp: model.concurrencyStamp,
          isActive: true,
          isDefault: !model.isDefault,
        },
        undefined,
        { skipHandleError: true },
      )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => this.load(),
        error: (error: unknown) => this.actionError.set(correlationIdFrom(error) ?? 'request'),
      });
  }
}
