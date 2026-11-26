import { signal } from '@angular/core';
import { provideRouter, convertToParamMap } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute } from '@angular/router';
import { of } from 'rxjs';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ResearchAccessService } from '../../shared/research-access.service';
import type { AxialVolume } from '../../shared/volume/nifti-volume';
import { SliceRendererService } from '../../shared/volume/slice-renderer.service';
import type { ResultState } from './result.store';
import { ResultStore } from './result.store';
import { ResultComponent } from './result.component';

describe('ResultComponent', () => {
  const source: AxialVolume = {
    width: 2,
    height: 2,
    depth: 3,
    voxels: new Float32Array(12).fill(1),
    spacing: [1, 1, 1],
    affine: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0],
  };
  const mask: AxialVolume = {
    ...source,
    voxels: new Float32Array(12),
  };
  const state = {
    kind: 'success',
    result: {
      id: 'result-1',
      concurrencyStamp: 'stamp',
      groundTruthSha256: null,
      evaluationProtocol: null,
      dice: null,
      ioU: null,
      precision: null,
      recall: null,
      inferenceMilliseconds: 12,
      preprocessingMilliseconds: 2,
      postprocessingMilliseconds: 1,
    },
    job: {
      id: 'job-1',
      requestedTime: '2026-01-01T00:00:00Z',
      completedTime: '2026-01-01T00:00:02Z',
      modelSemanticVersion: '1.0.0',
      preprocessingVersion: 'flair-v1',
    },
    study: { id: 'study-1', pseudonym: 'anon-1', hasGroundTruth: false },
    source,
    mask,
  } satisfies ResultState;
  const store = {
    state: signal(state),
    evaluationError: signal<string | null>(null),
    load: vi.fn(),
    evaluate: vi.fn(),
  };
  const renderer = { render: vi.fn() };

  beforeEach(() => {
    renderer.render.mockClear();
    TestBed.overrideComponent(ResultComponent, {
      set: { providers: [{ provide: ResultStore, useValue: store }] },
    });
    TestBed.configureTestingModule({
      imports: [ResultComponent],
      providers: [
        provideRouter([]),
        {
          provide: ActivatedRoute,
          useValue: { paramMap: of(convertToParamMap({ id: 'result-1' })) },
        },
        { provide: ResearchAccessService, useValue: { can$: () => of(false) } },
        { provide: SliceRendererService, useValue: renderer },
      ],
    });
  });

  it('does not present absent ground-truth metrics as zero', async () => {
    const fixture = TestBed.createComponent(ResultComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const host = fixture.nativeElement as HTMLElement;

    expect(host.textContent).toContain('未提供可评价的真实标签');
    expect(host.textContent).not.toContain('使用已登记真实标签评价');
    expect(
      [...host.querySelectorAll('dt')].some((item) => item.textContent?.trim() === 'Dice'),
    ).toBe(false);
    expect(host.textContent).not.toContain('0.000');
  });

  it('changes the viewed layer with keyboard input and rerenders on opacity changes', async () => {
    const fixture = TestBed.createComponent(ResultComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const host = fixture.nativeElement as HTMLElement;
    const stage = host.querySelector('.slice-stage');
    if (!(stage instanceof HTMLElement)) throw new Error('viewerStageMissing');

    stage.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    fixture.detectChanges();
    await fixture.whenStable();
    expect(fixture.componentInstance.slice()).toBe(1);
    expect(renderer.render).toHaveBeenLastCalledWith(
      expect.any(HTMLCanvasElement),
      source,
      1,
      'overlay',
      mask,
      0.45,
    );

    const opacity = host.querySelectorAll<HTMLInputElement>('input[type="range"]')[1];
    if (!opacity) throw new Error('opacityControlMissing');
    opacity.value = '0.7';
    opacity.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
    await fixture.whenStable();
    expect(fixture.componentInstance.opacity()).toBe(0.7);
    expect(renderer.render).toHaveBeenLastCalledWith(
      expect.any(HTMLCanvasElement),
      source,
      1,
      'overlay',
      mask,
      0.7,
    );
  });
});
