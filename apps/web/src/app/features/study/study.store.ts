import { DestroyRef, Injectable, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import type { Rest } from '@abp/ng.core';
import { HttpEventType } from '@angular/common/http';
import { EMPTY, Observable, catchError, finalize, map } from 'rxjs';
import {
  BrainStudyService,
  ModelVersionService,
  SegmentationJobService,
  type BrainStudyDto,
  type ModelVersionDto,
} from '../../proxy/research';
import { correlationIdFrom } from '../../shared/api-error';
import { SourceVolumeCacheService } from '../../shared/source-volume-cache.service';
import { sameGrid } from '../../shared/volume/nifti-volume';
import { inspectNiftiFile } from '../../shared/volume/nifti-file';
import type { InspectedNifti } from '../../shared/volume/nifti-file';

export type StudyListState =
  | { kind: 'loading' }
  | { kind: 'success'; studies: BrainStudyDto[]; totalCount: number }
  | { kind: 'empty' }
  | { kind: 'error'; correlationId: string | null };

export type StudyUploadState =
  | { kind: 'idle' }
  | { kind: 'uploading'; percent: number | null }
  | { kind: 'success'; study: BrainStudyDto; clientHashMatches: boolean }
  | { kind: 'error'; correlationId: string | null };

type UploadEvent =
  | { kind: 'progress'; loaded: number; total: number | null }
  | { kind: 'success'; study: BrainStudyDto }
  | { kind: 'started' };

@Injectable()
export class StudyStore {
  private readonly destroyRef = inject(DestroyRef);
  private readonly studiesApi = inject(BrainStudyService);
  private readonly modelsApi = inject(ModelVersionService);
  private readonly jobsApi = inject(SegmentationJobService);
  private readonly sourceCache = inject(SourceVolumeCacheService);

  readonly state = signal<StudyListState>({ kind: 'loading' });
  readonly uploadState = signal<StudyUploadState>({ kind: 'idle' });
  readonly models = signal<ModelVersionDto[]>([]);
  readonly modelError = signal<string | null>(null);
  readonly groundTruthBusyId = signal<string | null>(null);
  readonly groundTruthErrorId = signal<string | null>(null);
  readonly pageIndex = signal(0);
  private currentFilter = '';

  load(filter = this.currentFilter, pageIndex = this.pageIndex()): void {
    this.currentFilter = filter;
    this.pageIndex.set(Math.max(0, pageIndex));
    this.state.set({ kind: 'loading' });
    this.studiesApi
      .getList(
        {
          filter,
          skipCount: this.pageIndex() * 20,
          maxResultCount: 20,
          sorting: 'creationTime desc',
        },
        undefined,
        {
          skipHandleError: true,
        },
      )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          const studies = result.items ?? [];
          this.state.set(
            studies.length
              ? { kind: 'success', studies, totalCount: result.totalCount ?? studies.length }
              : { kind: 'empty' },
          );
        },
        error: (error: unknown) =>
          this.state.set({ kind: 'error', correlationId: correlationIdFrom(error) }),
      });

    this.modelsApi
      .getList({ isActive: true, skipCount: 0, maxResultCount: 100 }, undefined, {
        skipHandleError: true,
      })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        catchError(() => {
          this.modelError.set('unavailable');
          return EMPTY;
        }),
      )
      .subscribe({
        next: (result) => {
          this.models.set(result.items ?? []);
          this.modelError.set(null);
        },
      });
  }

  changePage(delta: number): void {
    const state = this.state();
    if (state.kind !== 'success') return;
    const nextPage = this.pageIndex() + delta;
    if (nextPage < 0 || nextPage * 20 >= state.totalCount) return;
    this.load(this.currentFilter, nextPage);
  }

  upload(studyNumber: string, pseudonym: string, sliceIndex: number, scan: InspectedNifti): void {
    const form = new FormData();
    form.append('StudyNumber', studyNumber);
    form.append('Pseudonym', pseudonym);
    form.append('SliceIndex', String(sliceIndex));
    form.append('File', scan.file, scan.file.name);
    this.uploadState.set({ kind: 'uploading', percent: 0 });

    const config: Partial<Rest.Config> & { reportProgress: boolean } = {
      observe: 'events' as Rest.Config['observe'],
      reportProgress: true,
      skipHandleError: true,
    };
    const events: Observable<unknown> = this.studiesApi.upload(form, undefined, config);
    events
      .pipe(
        map((event) => parseUploadEvent(event)),
        takeUntilDestroyed(this.destroyRef),
        catchError((error: unknown) => {
          this.uploadState.set({ kind: 'error', correlationId: correlationIdFrom(error) });
          return EMPTY;
        }),
        finalize(() => {
          if (this.uploadState().kind === 'uploading') this.uploadState.set({ kind: 'idle' });
        }),
      )
      .subscribe((event) => {
        if (event.kind === 'progress') {
          const percent =
            event.total && event.total > 0
              ? Math.min(99, Math.round((event.loaded / event.total) * 100))
              : null;
          this.uploadState.set({ kind: 'uploading', percent });
        } else if (event.kind === 'success') {
          if (event.study.id) {
            this.sourceCache.set(event.study.id, { file: scan.file, volume: scan.volume });
          }
          this.uploadState.set({
            kind: 'success',
            study: event.study,
            clientHashMatches: event.study.originalFileSha256 === scan.sha256,
          });
          this.load(this.currentFilter, 0);
        }
      });
  }

  async registerGroundTruth(study: BrainStudyDto, file: File): Promise<void> {
    const studyId = study.id;
    if (!studyId) return;
    this.groundTruthBusyId.set(studyId);
    this.groundTruthErrorId.set(null);
    try {
      const truth = await inspectNiftiFile(file);
      if (truth.volume.width !== study.width || truth.volume.height !== study.height) {
        this.groundTruthErrorId.set(studyId);
        return;
      }
      const source = this.sourceCache.get(studyId);
      if (source && !sameGrid(source.volume, truth.volume)) {
        this.groundTruthErrorId.set(studyId);
        return;
      }
      const form = new FormData();
      form.append('File', file, file.name);
      await new Promise<void>((resolve, reject) => {
        this.studiesApi
          .registerGroundTruth(studyId, form, undefined, { skipHandleError: true })
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: () => resolve(),
            error: (error: unknown) => reject(error),
          });
      });
      this.load();
    } catch (error: unknown) {
      this.groundTruthErrorId.set(studyId);
      if (error instanceof Error && error.message === 'invalidNifti') {
        this.groundTruthErrorId.set(studyId);
      }
    } finally {
      this.groundTruthBusyId.set(null);
    }
  }

  createJob(studyId: string, modelVersionId: string) {
    return this.jobsApi.create(
      { studyId, modelVersionId, idempotencyKey: crypto.randomUUID() },
      undefined,
      { skipHandleError: true },
    );
  }
}

function parseUploadEvent(value: unknown): UploadEvent {
  if (!isRecord(value) || !('type' in value)) {
    return isStudyDto(value) ? { kind: 'success', study: value } : { kind: 'started' };
  }
  if (value['type'] === HttpEventType.UploadProgress && typeof value['loaded'] === 'number') {
    return {
      kind: 'progress',
      loaded: value['loaded'],
      total: typeof value['total'] === 'number' ? value['total'] : null,
    };
  }
  if (value['type'] === HttpEventType.Response && isRecord(value['body'])) {
    return isStudyDto(value['body'])
      ? { kind: 'success', study: value['body'] }
      : { kind: 'started' };
  }
  return { kind: 'started' };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function isStudyDto(value: unknown): value is BrainStudyDto {
  return (
    isRecord(value) &&
    typeof value['id'] === 'string' &&
    typeof value['originalFileSha256'] === 'string'
  );
}
