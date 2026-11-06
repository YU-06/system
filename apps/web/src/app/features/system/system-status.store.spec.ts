import { HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SystemService, SystemStatusDto } from '../../proxy/system';
import { SystemStatusStore } from './system-status.store';

describe('SystemStatusStore', () => {
  let response: Subject<SystemStatusDto>;
  const get = vi.fn();

  beforeEach(() => {
    response = new Subject<SystemStatusDto>();
    get.mockReturnValue(response.asObservable());
    TestBed.configureTestingModule({ providers: [{ provide: SystemService, useValue: { get } }] });
  });
  afterEach(() => vi.clearAllMocks());

  it('moves from loading to a real response and deduplicates pending refreshes', () => {
    const store = TestBed.inject(SystemStatusStore);
    expect(store.state().kind).toBe('loading');
    store.refresh();
    expect(get).toHaveBeenCalledTimes(1);
    response.next({ service: 'brainseg-backend', status: 'ok' });
    response.complete();
    expect(store.state().kind).toBe('success');
  });

  it('represents an empty result without fabricating a service', () => {
    const store = TestBed.inject(SystemStatusStore);
    response.next({});
    response.complete();
    expect(store.state().kind).toBe('empty');
  });

  it('preserves only the safe correlation response header on an error', () => {
    const store = TestBed.inject(SystemStatusStore);
    response.error(
      new HttpErrorResponse({
        status: 503,
        headers: new HttpHeaders({ 'X-Correlation-Id': 'research-123' }),
        error: { secret: 'must not be displayed' },
      }),
    );
    expect(store.state()).toEqual({ kind: 'error', correlationId: 'research-123' });
    expect(JSON.stringify(store.state())).not.toContain('secret');
  });

  it('can retry after an error', () => {
    const store = TestBed.inject(SystemStatusStore);
    response.error(new Error('offline'));
    const retry = new Subject<SystemStatusDto>();
    get.mockReturnValue(retry.asObservable());
    store.refresh();
    retry.next({ service: 'brainseg-backend' });
    retry.complete();
    expect(store.state().kind).toBe('success');
  });
});
