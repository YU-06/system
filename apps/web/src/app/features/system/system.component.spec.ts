import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SystemComponent } from './system.component';
import { SystemState, SystemStatusStore } from './system-status.store';

describe('SystemComponent', () => {
  const state = signal<SystemState>({ kind: 'loading' });
  const refresh = vi.fn();

  beforeEach(() => {
    state.set({ kind: 'loading' });
    refresh.mockClear();
    TestBed.configureTestingModule({
      imports: [SystemComponent],
      providers: [{ provide: SystemStatusStore, useValue: { state, refresh } }],
    });
  });

  it('renders loading and prevents duplicate refreshes', async () => {
    const fixture = TestBed.createComponent(SystemComponent);
    await fixture.whenStable();
    const host = fixture.nativeElement as HTMLElement;
    expect(host.textContent).toContain('连接中');
    expect(host.querySelector('button')?.disabled).toBe(true);
  });

  it('renders a recoverable error without raw backend details', async () => {
    state.set({ kind: 'error', correlationId: 'research-123' });
    const fixture = TestBed.createComponent(SystemComponent);
    await fixture.whenStable();
    const host = fixture.nativeElement as HTMLElement;
    expect(host.querySelector('[role="alert"]')?.textContent).toContain('服务连接失败');
    expect(host.textContent).toContain('research-123');
    host.querySelector('button')?.click();
    expect(refresh).toHaveBeenCalledOnce();
  });

  it('renders empty and success states distinctly', async () => {
    state.set({ kind: 'empty' });
    const fixture = TestBed.createComponent(SystemComponent);
    await fixture.whenStable();
    const host = fixture.nativeElement as HTMLElement;
    expect(host.textContent).toContain('暂无服务状态');
    state.set({
      kind: 'success',
      data: { service: 'brainseg-backend', serverTimeUtc: '2026-11-06T00:00:00Z' },
    });
    await fixture.whenStable();
    expect(host.textContent).toContain('brainseg-backend');
    expect(host.textContent).toContain('2026-11-06 00:00:00');
    expect(host.textContent).toContain('暂无已执行实验');
  });
});
