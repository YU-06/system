import { DestroyRef, Injectable, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { EMPTY, catchError, finalize, forkJoin, from, map, of, switchMap } from 'rxjs';
import {
  BrainStudyService,
  SegmentationJobService,
  SegmentationResultService,
  type BrainStudyDto,
  type SegmentationJobDto,
  type SegmentationResultDto,
} from '../../proxy/research';
import { correlationIdFrom } from '../../shared/api-error';
import { SourceVolumeCacheService } from '../../shared/source-volume-cache.service';
import { readNiftiVolume, sameGrid, type AxialVolume } from '../../shared/volume/nifti-volume';

export type ResultState =
  | { kind: 'loading' }
  | {
      kind: 'success';
      result: SegmentationResultDto;
      job: SegmentationJobDto;
      study: BrainStudyDto;
      source: AxialVolume;
      mask: AxialVolume;
      boundary?: AxialVolume;
      uncertainty?: AxialVolume;
    }
  | {
      kind: 'error';
      reason: 'request' | 'sourceMissing' | 'invalidMask' | 'invalidAuxiliary';
      correlationId: string | null;
    };

@Injectable()
export class ResultStore {
  private readonly destroyRef = inject(DestroyRef);
  private readonly resultsApi = inject(SegmentationResultService);
  private readonly jobsApi = inject(SegmentationJobService);
  private readonly studiesApi = inject(BrainStudyService);
  private readonly cache = inject(SourceVolumeCacheService);

  readonly state = signal<ResultState>({ kind: 'loading' });
  readonly evaluationError = signal<string | null>(null);
  readonly evaluationBusy = signal(false);

  load(resultId: string): void {
    this.state.set({ kind: 'loading' });
    this.resultsApi
      .get(resultId, undefined, { skipHandleError: true })
      .pipe(
        switchMap((result) => {
          if (!result.jobId) throw new Error('invalidResult');
          return this.jobsApi
            .get(result.jobId, undefined, { skipHandleError: true })
            .pipe(map((job) => ({ result, job })));
        }),
        switchMap(({ result, job }) => {
          const resultId = result.id;
          if (!job.studyId || !resultId) throw new Error('invalidStudy');
          return this.studiesApi.get(job.studyId, undefined, { skipHandleError: true }).pipe(
            switchMap((study) => {
              const cached = study.id ? this.cache.get(study.id) : undefined;
              if (!cached) throw new Error('sourceMissing');
              return this.resultsApi
                .downloadMask(resultId, undefined, { skipHandleError: true })
                .pipe(
                  switchMap((blob) =>
                    from(readNiftiVolume(blob)).pipe(
                      switchMap((mask) =>
                        forkJoin({
                          boundary: result.boundaryObjectKey
                            ? this.resultsApi
                                .downloadArtifact(resultId, 'boundary', undefined, {
                                  skipHandleError: true,
                                })
                                .pipe(switchMap((artifact) => from(readNiftiVolume(artifact))))
                            : of(undefined),
                          uncertainty: result.uncertaintyObjectKey
                            ? this.resultsApi
                                .downloadArtifact(resultId, 'uncertainty', undefined, {
                                  skipHandleError: true,
                                })
                                .pipe(switchMap((artifact) => from(readNiftiVolume(artifact))))
                            : of(undefined),
                        }).pipe(
                          map(({ boundary, uncertainty }) => ({
                            result,
                            job,
                            study,
                            source: cached.volume,
                            mask,
                            boundary,
                            uncertainty,
                          })),
                        ),
                      ),
                    ),
                  ),
                );
            }),
          );
        }),
        map((value) => {
          if (!sameGrid(value.source, value.mask) || !isBinaryMask(value.mask)) {
            throw new Error('invalidMask');
          }
          if (
            (value.boundary &&
              (!sameGrid(value.source, value.boundary) || !isBinaryMask(value.boundary))) ||
            (value.uncertainty &&
              (!sameGrid(value.source, value.uncertainty) || !isUncertaintyMap(value.uncertainty)))
          ) {
            throw new Error('invalidAuxiliary');
          }
          return value;
        }),
        takeUntilDestroyed(this.destroyRef),
        catchError((error: unknown) => {
          const reason =
            error instanceof Error && error.message === 'sourceMissing'
              ? 'sourceMissing'
              : error instanceof Error && error.message === 'invalidMask'
                ? 'invalidMask'
                : error instanceof Error && error.message === 'invalidAuxiliary'
                  ? 'invalidAuxiliary'
                  : 'request';
          this.state.set({
            kind: 'error',
            reason,
            correlationId: correlationIdFrom(error),
          });
          return EMPTY;
        }),
      )
      .subscribe((value) => this.state.set({ kind: 'success', ...value }));
  }

  evaluate(result: SegmentationResultDto): void {
    if (this.evaluationBusy() || !result.id || !result.concurrencyStamp) return;
    const resultId = result.id;
    this.evaluationError.set(null);
    this.evaluationBusy.set(true);
    this.resultsApi
      .evaluate(result.id, { concurrencyStamp: result.concurrencyStamp }, undefined, {
        skipHandleError: true,
      })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.evaluationBusy.set(false)),
      )
      .subscribe({
        next: () => this.load(resultId),
        error: (error: unknown) => this.evaluationError.set(correlationIdFrom(error) ?? 'request'),
      });
  }
}

function isBinaryMask(mask: AxialVolume): boolean {
  for (const value of mask.voxels) {
    if (value !== 0 && value !== 1) return false;
  }
  return true;
}

function isUncertaintyMap(volume: AxialVolume): boolean {
  for (const value of volume.voxels) {
    if (!Number.isFinite(value) || value < 0 || value > 100) return false;
  }
  return true;
}
