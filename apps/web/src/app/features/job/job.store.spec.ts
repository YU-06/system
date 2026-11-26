import { HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { throwError } from 'rxjs';
import { describe, expect, it } from 'vitest';
import { SegmentationJobService, SegmentationResultService } from '../../proxy/research';
import { JobStore } from './job.store';

describe('JobStore', () => {
  it('surfaces API failures and correlation identifiers as an error state', () => {
    const apiError = new HttpErrorResponse({
      status: 503,
      headers: new HttpHeaders({ 'X-Correlation-Id': 'corr-job-503' }),
    });
    TestBed.configureTestingModule({
      providers: [
        JobStore,
        {
          provide: SegmentationJobService,
          useValue: { getList: () => throwError(() => apiError) },
        },
        {
          provide: SegmentationResultService,
          useValue: { getList: () => throwError(() => apiError) },
        },
      ],
    });
    const store = TestBed.inject(JobStore);
    store.loadList();

    expect(store.listState()).toEqual({ kind: 'error', correlationId: 'corr-job-503' });
  });
});
