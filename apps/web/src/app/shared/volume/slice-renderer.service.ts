import { Injectable } from '@angular/core';
import { renderSlice, type AxialVolume } from './nifti-volume';

@Injectable({ providedIn: 'root' })
export class SliceRendererService {
  render(
    canvas: HTMLCanvasElement,
    source: AxialVolume,
    slice: number,
    mode: 'source' | 'mask' | 'overlay' | 'contour',
    mask: AxialVolume | undefined,
    opacity: number,
  ): void {
    renderSlice(canvas, source, slice, mode, mask, opacity);
  }
}
