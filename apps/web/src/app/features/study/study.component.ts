import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { AsyncPipe } from '@angular/common';
import { I18nService } from '../../localization/i18n.service';
import {
  BrainStudyStatus,
  ModelArchitecture,
  type BrainStudyDto,
  type ModelVersionDto,
} from '../../proxy/research';
import { ResearchAccessService } from '../../shared/research-access.service';
import { correlationIdFrom } from '../../shared/api-error';
import { SourceVolumeCacheService } from '../../shared/source-volume-cache.service';
import { inspectNiftiFile, type InspectedNifti } from '../../shared/volume/nifti-file';
import { StudyStore } from './study.store';

@Component({
  selector: 'app-study',
  imports: [AsyncPipe, DecimalPipe, ReactiveFormsModule],
  providers: [StudyStore],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './study.component.html',
})
export class StudyComponent {
  readonly text = inject(I18nService).text;
  readonly access = inject(ResearchAccessService);
  readonly store = inject(StudyStore);
  private readonly router = inject(Router);
  private readonly sourceCache = inject(SourceVolumeCacheService);

  readonly canUpload$ = this.access.can$('BrainSeg.BrainStudies.Create');
  readonly canCreateJob$ = this.access.canAll$([
    'BrainSeg.SegmentationJobs',
    'BrainSeg.SegmentationJobs.Create',
  ]);
  readonly canRegisterGroundTruth$ = this.access.can$('BrainSeg.BrainStudies.RegisterGroundTruth');
  readonly selectedFile = signal<File | null>(null);
  readonly inspected = signal<InspectedNifti | null>(null);
  readonly inspectionError = signal<string | null>(null);
  readonly inspecting = signal(false);
  readonly filter = new FormControl('', { nonNullable: true });
  readonly uploadForm = new FormGroup({
    studyNumber: new FormControl('', {
      nonNullable: true,
      validators: [Validators.required, Validators.maxLength(64)],
    }),
    pseudonym: new FormControl('', {
      nonNullable: true,
      validators: [Validators.required, Validators.maxLength(64)],
    }),
    sliceIndex: new FormControl(0, {
      nonNullable: true,
      validators: [Validators.min(0), Validators.max(511)],
    }),
  });
  readonly selectedModelId = signal('');
  readonly jobError = signal<string | null>(null);

  constructor() {
    this.store.load();
  }

  filterStudies(): void {
    this.store.load(this.filter.value.trim(), 0);
  }

  changePage(delta: number): void {
    this.store.changePage(delta);
  }

  async selectFile(file: File | undefined): Promise<void> {
    this.selectedFile.set(file ?? null);
    this.inspected.set(null);
    this.inspectionError.set(null);
    if (!file) return;
    this.inspecting.set(true);
    try {
      this.inspected.set(await inspectNiftiFile(file));
    } catch (error: unknown) {
      this.inspectionError.set(this.fileErrorMessage(error));
    } finally {
      this.inspecting.set(false);
    }
  }

  async onDrop(event: DragEvent): Promise<void> {
    event.preventDefault();
    await this.selectFile(event.dataTransfer?.files.item(0) ?? undefined);
  }

  preventDrop(event: DragEvent): void {
    event.preventDefault();
  }

  async submitUpload(): Promise<void> {
    const scan = this.inspected();
    const value = this.uploadForm.getRawValue();
    if (!scan || this.uploadForm.invalid) {
      this.uploadForm.markAllAsTouched();
      return;
    }
    if (value.sliceIndex >= scan.volume.depth) {
      this.uploadForm.controls.sliceIndex.setErrors({ sliceOutsideVolume: true });
      this.uploadForm.controls.sliceIndex.markAsTouched();
      return;
    }
    this.uploadForm.controls.sliceIndex.setErrors(null);
    this.store.upload(value.studyNumber.trim(), value.pseudonym.trim(), value.sliceIndex, scan);
  }

  async registerGroundTruth(study: BrainStudyDto, event: Event): Promise<void> {
    const input = event.target;
    if (!(input instanceof HTMLInputElement)) return;
    const file = input.files?.item(0);
    if (file) await this.store.registerGroundTruth(study, file);
    input.value = '';
  }

  async createJob(studyId: string): Promise<void> {
    const modelVersionId = this.selectedModelId();
    if (!modelVersionId) return;
    this.jobError.set(null);
    this.store.createJob(studyId, modelVersionId).subscribe({
      next: (job) => {
        if (job.id) void this.router.navigate(['/jobs', job.id]);
      },
      error: (error: unknown) => this.jobError.set(correlationIdFrom(error) ?? 'request'),
    });
  }

  selectModel(event: Event): void {
    if (event.target instanceof HTMLSelectElement) this.selectedModelId.set(event.target.value);
  }

  localDepth(studyId: string | undefined): string {
    const depth = studyId ? this.sourceCache.get(studyId)?.volume.depth : undefined;
    return depth ? ` × ${depth}` : '';
  }

  studyStatusLabel(status: BrainStudyDto['status']): string {
    switch (status) {
      case BrainStudyStatus.Uploaded:
        return this.text.studyUploaded;
      case BrainStudyStatus.Ready:
        return this.text.studyReady;
      case BrainStudyStatus.Archived:
        return this.text.studyArchived;
      default:
        return this.text.unknownStatus;
    }
  }

  architectureLabel(architecture: ModelVersionDto['architecture']): string {
    return architecture === ModelArchitecture.AttentionUNet
      ? this.text.attentionUNet
      : architecture === ModelArchitecture.UNet
        ? this.text.unet
        : this.text.notAvailable;
  }

  private fileErrorMessage(error: unknown): string {
    if (!(error instanceof Error)) return this.text.invalidNifti;
    switch (error.message) {
      case 'invalidFileType':
        return this.text.invalidFileType;
      case 'uploadTooLarge':
        return this.text.uploadTooLarge;
      case 'expandedTooLarge':
        return this.text.expandedTooLarge;
      case 'invalidDimensions':
        return this.text.invalidDimensions;
      case 'invalidDatatype':
        return this.text.invalidDatatype;
      case 'gzipUnsupported':
        return this.text.gzipUnsupported;
      case 'invalidSpatialMetadata':
        return this.text.invalidSpatialMetadata;
      default:
        return this.text.invalidNifti;
    }
  }
}
