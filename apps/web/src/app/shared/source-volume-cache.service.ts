import { Injectable } from '@angular/core';
import type { AxialVolume } from './volume/nifti-volume';

export interface CachedStudyVolume {
  file: File;
  volume: AxialVolume;
}

@Injectable({ providedIn: 'root' })
export class SourceVolumeCacheService {
  private readonly volumes = new Map<string, CachedStudyVolume>();
  private readonly maximumBytes = 192 * 1024 * 1024;
  private cachedBytes = 0;

  set(studyId: string, value: CachedStudyVolume): void {
    const previous = this.volumes.get(studyId);
    if (previous) {
      this.cachedBytes -= sizeOf(previous);
      this.volumes.delete(studyId);
    }
    this.volumes.set(studyId, value);
    this.cachedBytes += sizeOf(value);
    while (this.cachedBytes > this.maximumBytes && this.volumes.size > 1) {
      const oldest = this.volumes.keys().next();
      if (oldest.done) break;
      const cached = this.volumes.get(oldest.value);
      this.volumes.delete(oldest.value);
      if (cached) this.cachedBytes -= sizeOf(cached);
    }
  }

  get(studyId: string): CachedStudyVolume | undefined {
    const cached = this.volumes.get(studyId);
    if (cached) {
      this.volumes.delete(studyId);
      this.volumes.set(studyId, cached);
    }
    return cached;
  }
}

function sizeOf(value: CachedStudyVolume): number {
  return value.file.size + value.volume.voxels.byteLength;
}
