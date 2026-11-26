import { AsyncPipe, DecimalPipe, PercentPipe } from '@angular/common';
import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  ViewChild,
  effect,
  inject,
  signal,
} from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { I18nService } from '../../localization/i18n.service';
import { SegmentationResultDto } from '../../proxy/research';
import { ResearchAccessService } from '../../shared/research-access.service';
import { SliceRendererService } from '../../shared/volume/slice-renderer.service';
import { ResultStore } from './result.store';

type ViewMode = 'source' | 'mask' | 'overlay' | 'contour' | 'compare';

@Component({
  selector: 'app-result-viewer',
  imports: [AsyncPipe, DecimalPipe, PercentPipe, RouterLink],
  providers: [ResultStore],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './result.component.html',
})
export class ResultComponent implements AfterViewInit {
  readonly text = inject(I18nService).text;
  readonly store = inject(ResultStore);
  readonly access = inject(ResearchAccessService);
  private readonly renderer = inject(SliceRendererService);
  readonly canEvaluate$ = this.access.can$('BrainSeg.SegmentationResults.Evaluate');
  readonly mode = signal<ViewMode>('overlay');
  readonly slice = signal(0);
  readonly opacity = signal(0.45);
  readonly zoom = signal(100);
  private readonly destroyRef = inject(DestroyRef);
  private readonly route = inject(ActivatedRoute);
  private initialized = false;

  @ViewChild('mainCanvas') private mainCanvas?: ElementRef<HTMLCanvasElement>;
  @ViewChild('compareSourceCanvas') private compareSourceCanvas?: ElementRef<HTMLCanvasElement>;
  @ViewChild('compareOverlayCanvas') private compareOverlayCanvas?: ElementRef<HTMLCanvasElement>;

  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      const id = params.get('id');
      if (id) this.store.load(id);
    });
    effect(() => {
      this.store.state();
      this.mode();
      this.slice();
      this.opacity();
      this.zoom();
      if (this.initialized) queueMicrotask(() => this.draw());
    });
  }

  ngAfterViewInit(): void {
    this.initialized = true;
    this.draw();
  }

  setMode(mode: ViewMode): void {
    this.mode.set(mode);
  }

  onKeydown(event: KeyboardEvent, depth: number): void {
    if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') {
      event.preventDefault();
      this.slice.update((value) => Math.max(0, value - 1));
    } else if (event.key === 'ArrowRight' || event.key === 'ArrowUp') {
      event.preventDefault();
      this.slice.update((value) => Math.min(depth - 1, value + 1));
    } else if (event.key === 'Home') {
      event.preventDefault();
      this.slice.set(0);
    } else if (event.key === 'End') {
      event.preventDefault();
      this.slice.set(depth - 1);
    }
  }

  updateSlice(event: Event): void {
    const target = event.target;
    if (target instanceof HTMLInputElement) this.slice.set(Number(target.value));
  }

  updateOpacity(event: Event): void {
    const target = event.target;
    if (target instanceof HTMLInputElement) this.opacity.set(Number(target.value));
  }

  updateZoom(event: Event): void {
    const target = event.target;
    if (target instanceof HTMLInputElement) this.zoom.set(Number(target.value));
  }

  metricsAvailable(result: SegmentationResultDto): boolean {
    return (
      Boolean(result.groundTruthSha256 && result.evaluationProtocol) &&
      [result.dice, result.ioU, result.precision, result.recall].every(
        (value) => typeof value === 'number' && Number.isFinite(value),
      )
    );
  }

  endToEndMilliseconds(requested?: string, completed?: string | null): number | null {
    if (!requested || !completed) return null;
    const elapsed = new Date(completed).getTime() - new Date(requested).getTime();
    return Number.isFinite(elapsed) && elapsed >= 0 ? elapsed : null;
  }

  sliceForwardMilliseconds(inference?: number, depth?: number): number | null {
    if (typeof inference !== 'number' || !depth || depth < 1) return null;
    return inference / depth;
  }

  private draw(): void {
    const state = this.store.state();
    if (state.kind !== 'success') return;
    const { source, mask } = state;
    const mode = this.mode();
    if (mode === 'compare') {
      if (this.compareSourceCanvas?.nativeElement) {
        this.renderer.render(
          this.compareSourceCanvas.nativeElement,
          source,
          this.slice(),
          'source',
          mask,
          this.opacity(),
        );
      }
      if (this.compareOverlayCanvas?.nativeElement) {
        this.renderer.render(
          this.compareOverlayCanvas.nativeElement,
          source,
          this.slice(),
          'overlay',
          mask,
          this.opacity(),
        );
      }
      return;
    }
    if (this.mainCanvas?.nativeElement) {
      this.renderer.render(
        this.mainCanvas.nativeElement,
        source,
        this.slice(),
        mode,
        mask,
        this.opacity(),
      );
    }
  }
}
