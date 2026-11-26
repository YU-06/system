import { AsyncPipe, DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, inject } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { SegmentationJobStatus, type SegmentationJobDto } from '../../proxy/research';
import { I18nService } from '../../localization/i18n.service';
import { ResearchAccessService } from '../../shared/research-access.service';
import { JobStore } from './job.store';

@Component({
  selector: 'app-job-list',
  imports: [AsyncPipe, DatePipe, ReactiveFormsModule, RouterLink],
  providers: [JobStore],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './job-list.component.html',
})
export class JobListComponent {
  readonly text = inject(I18nService).text;
  readonly store = inject(JobStore);
  readonly access = inject(ResearchAccessService);
  readonly canCancel$ = this.access.can$('BrainSeg.SegmentationJobs.Cancel');
  readonly canRetry$ = this.access.can$('BrainSeg.SegmentationJobs.Retry');
  readonly filter = new FormControl('', { nonNullable: true });
  readonly status = new FormControl('', { nonNullable: true });
  readonly statuses = Object.values(SegmentationJobStatus);

  constructor() {
    this.load();
  }

  load(): void {
    const status = this.status.value
      ? this.statuses.find((value) => value === this.status.value)
      : undefined;
    this.store.loadList(this.filter.value.trim(), status, 0);
  }

  changePage(delta: number): void {
    this.store.changePage(delta);
  }

  stateLabel(status: SegmentationJobDto['status']): string {
    switch (status) {
      case SegmentationJobStatus.Pending:
        return this.text.jobPending;
      case SegmentationJobStatus.Running:
        return this.text.jobRunning;
      case SegmentationJobStatus.Succeeded:
        return this.text.jobSucceeded;
      case SegmentationJobStatus.Failed:
        return this.text.jobFailed;
      case SegmentationJobStatus.Cancelled:
        return this.text.jobCancelled;
      default:
        return this.text.unknownStatus;
    }
  }

  cancel(job: SegmentationJobDto): void {
    this.store.cancel(job);
  }

  retry(job: SegmentationJobDto): void {
    this.store.retry(job);
  }
}

@Component({
  selector: 'app-job-detail',
  imports: [AsyncPipe, RouterLink],
  providers: [JobStore],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './job-detail.component.html',
})
export class JobDetailComponent {
  readonly text = inject(I18nService).text;
  readonly store = inject(JobStore);
  readonly access = inject(ResearchAccessService);
  readonly canCancel$ = this.access.can$('BrainSeg.SegmentationJobs.Cancel');
  readonly canRetry$ = this.access.can$('BrainSeg.SegmentationJobs.Retry');
  private readonly destroyRef = inject(DestroyRef);
  private readonly route = inject(ActivatedRoute);

  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      const id = params.get('id');
      if (id) this.store.loadDetail(id);
    });
  }

  stateLabel(status: SegmentationJobDto['status']): string {
    switch (status) {
      case SegmentationJobStatus.Pending:
        return this.text.jobPending;
      case SegmentationJobStatus.Running:
        return this.text.jobRunning;
      case SegmentationJobStatus.Succeeded:
        return this.text.jobSucceeded;
      case SegmentationJobStatus.Failed:
        return this.text.jobFailed;
      case SegmentationJobStatus.Cancelled:
        return this.text.jobCancelled;
      default:
        return this.text.unknownStatus;
    }
  }
}
