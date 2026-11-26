import { DestroyRef, Injectable, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { EMPTY, Subscription, catchError, exhaustMap, finalize, map, timer } from 'rxjs';
import {
  SegmentationJobService,
  SegmentationResultService,
  type SegmentationJobDto,
  type SegmentationJobListInput,
} from '../../proxy/research';
import { SegmentationJobStatus } from '../../proxy/research/segmentation-job-status.enum';
import { correlationIdFrom } from '../../shared/api-error';

export type JobListState =
  | { kind: 'loading' }
  | { kind: 'success'; jobs: SegmentationJobDto[]; totalCount: number }
  | { kind: 'empty' }
  | { kind: 'error'; correlationId: string | null };

export type JobDetailState =
  | { kind: 'loading' }
  | { kind: 'success'; job: SegmentationJobDto }
  | { kind: 'error'; correlationId: string | null };

@Injectable()
export class JobStore {
  private readonly destroyRef = inject(DestroyRef);
  private readonly jobsApi = inject(SegmentationJobService);
  private readonly resultsApi = inject(SegmentationResultService);
  private listPolling?: Subscription;
  private detailPolling?: Subscription;
  private listQuery: SegmentationJobListInput = {
    skipCount: 0,
    maxResultCount: 20,
    sorting: 'requestedTime desc',
  };
  readonly pageIndex = signal(0);

  readonly listState = signal<JobListState>({ kind: 'loading' });
  readonly detailState = signal<JobDetailState>({ kind: 'loading' });
  readonly transientPollError = signal(false);
  readonly resultId = signal<string | null>(null);
  readonly resultLoadError = signal<string | null>(null);
  readonly actionError = signal<string | null>(null);

  loadList(filter = '', status?: SegmentationJobStatus, pageIndex = 0): void {
    this.listPolling?.unsubscribe();
    this.pageIndex.set(Math.max(0, pageIndex));
    this.listQuery = {
      filter: filter || undefined,
      status,
      skipCount: this.pageIndex() * 20,
      maxResultCount: 20,
      sorting: 'requestedTime desc',
    };
    this.listState.set({ kind: 'loading' });
    this.transientPollError.set(false);
    this.jobsApi
      .getList(this.listQuery, undefined, { skipHandleError: true })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          const jobs = result.items ?? [];
          this.setList(jobs, result.totalCount ?? jobs.length);
          if (jobs.some(isActiveJob)) this.startListPolling();
        },
        error: (error: unknown) =>
          this.listState.set({ kind: 'error', correlationId: correlationIdFrom(error) }),
      });
  }

  changePage(delta: number): void {
    const state = this.listState();
    if (state.kind !== 'success') return;
    const nextPage = this.pageIndex() + delta;
    if (nextPage < 0 || nextPage * 20 >= state.totalCount) return;
    this.loadList(this.listQuery.filter ?? '', this.listQuery.status ?? undefined, nextPage);
  }

  loadDetail(jobId: string): void {
    this.detailPolling?.unsubscribe();
    this.resultId.set(null);
    this.resultLoadError.set(null);
    this.transientPollError.set(false);
    this.detailState.set({ kind: 'loading' });
    this.jobsApi
      .get(jobId, undefined, { skipHandleError: true })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (job) => {
          this.detailState.set({ kind: 'success', job });
          if (job.status === SegmentationJobStatus.Succeeded) this.loadResult(job.id);
          if (isActiveJob(job)) this.startDetailPolling(jobId);
        },
        error: (error: unknown) =>
          this.detailState.set({ kind: 'error', correlationId: correlationIdFrom(error) }),
      });
  }

  cancel(job: SegmentationJobDto): void {
    if (!job.id || !job.concurrencyStamp) return;
    this.actionError.set(null);
    this.jobsApi
      .cancel(job.id, { concurrencyStamp: job.concurrencyStamp }, undefined, {
        skipHandleError: true,
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated) => {
          this.updateJob(updated);
          if (updated.id) this.detailState.set({ kind: 'success', job: updated });
          if (!isActiveJob(updated)) {
            this.detailPolling?.unsubscribe();
            const list = this.listState();
            if (list.kind === 'success' && !list.jobs.some(isActiveJob)) {
              this.listPolling?.unsubscribe();
            }
          }
        },
        error: (error: unknown) => this.actionError.set(correlationIdFrom(error) ?? 'request'),
      });
  }

  retry(job: SegmentationJobDto): void {
    if (!job.id || !job.concurrencyStamp) return;
    this.actionError.set(null);
    this.jobsApi
      .retry(job.id, { concurrencyStamp: job.concurrencyStamp }, undefined, {
        skipHandleError: true,
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated) => {
          this.updateJob(updated);
          this.detailState.set({ kind: 'success', job: updated });
          if (isActiveJob(updated)) {
            if (updated.id) this.startDetailPolling(updated.id);
            const list = this.listState();
            if (list.kind === 'success' && list.jobs.some(isActiveJob)) this.startListPolling();
          }
        },
        error: (error: unknown) => this.actionError.set(correlationIdFrom(error) ?? 'request'),
      });
  }

  stopPolling(): void {
    this.listPolling?.unsubscribe();
    this.detailPolling?.unsubscribe();
  }

  private startListPolling(): void {
    this.listPolling?.unsubscribe();
    this.listPolling = timer(2000, 2000)
      .pipe(
        exhaustMap(() =>
          this.jobsApi.getList(this.listQuery, undefined, { skipHandleError: true }).pipe(
            map((result) => ({ kind: 'success' as const, result })),
            catchError(() => {
              this.transientPollError.set(true);
              return EMPTY;
            }),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
        finalize(() => (this.listPolling = undefined)),
      )
      .subscribe(({ result }) => {
        this.transientPollError.set(false);
        const jobs = result.items ?? [];
        this.setList(jobs, result.totalCount ?? jobs.length);
        if (!jobs.some(isActiveJob)) this.listPolling?.unsubscribe();
      });
  }

  private startDetailPolling(jobId: string): void {
    this.detailPolling?.unsubscribe();
    this.detailPolling = timer(2000, 2000)
      .pipe(
        exhaustMap(() =>
          this.jobsApi.get(jobId, undefined, { skipHandleError: true }).pipe(
            map((job) => ({ kind: 'success' as const, job })),
            catchError(() => {
              this.transientPollError.set(true);
              return EMPTY;
            }),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
        finalize(() => (this.detailPolling = undefined)),
      )
      .subscribe(({ job }) => {
        this.transientPollError.set(false);
        this.detailState.set({ kind: 'success', job });
        if (job.status === SegmentationJobStatus.Succeeded) this.loadResult(job.id);
        if (!isActiveJob(job)) this.detailPolling?.unsubscribe();
      });
  }

  private loadResult(jobId: string | undefined): void {
    if (!jobId) return;
    this.resultLoadError.set(null);
    this.resultsApi
      .getList({ jobId, skipCount: 0, maxResultCount: 1 }, undefined, { skipHandleError: true })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => this.resultId.set(result.items?.[0]?.id ?? null),
        error: (error: unknown) => {
          this.resultId.set(null);
          this.resultLoadError.set(correlationIdFrom(error) ?? 'request');
        },
      });
  }

  retryResult(jobId: string | undefined): void {
    if (jobId) this.loadResult(jobId);
  }

  private setList(jobs: SegmentationJobDto[], totalCount: number): void {
    this.listState.set(jobs.length ? { kind: 'success', jobs, totalCount } : { kind: 'empty' });
  }

  private updateJob(updated: SegmentationJobDto): void {
    const state = this.listState();
    if (state.kind !== 'success') return;
    this.setList(
      state.jobs.map((job) => (job.id === updated.id ? updated : job)),
      state.totalCount,
    );
  }
}

function isActiveJob(job: SegmentationJobDto): boolean {
  return (
    job.status === SegmentationJobStatus.Pending || job.status === SegmentationJobStatus.Running
  );
}
