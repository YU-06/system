import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { I18nService } from '../../localization/i18n.service';
import { ExperimentStore } from './experiment.store';

@Component({
  selector: 'app-experiment-history',
  imports: [ReactiveFormsModule],
  providers: [ExperimentStore],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './experiment.component.html',
})
export class ExperimentComponent {
  readonly text = inject(I18nService).text;
  readonly store = inject(ExperimentStore);
  readonly filter = new FormControl('', { nonNullable: true });
  readonly seed = new FormControl('', { nonNullable: true });
  readonly filterError = signal(false);

  constructor() {
    this.store.load();
  }

  load(): void {
    const seedValue = this.seed.value.trim();
    const parsedSeed = seedValue ? Number(seedValue) : undefined;
    this.filterError.set(
      Boolean(seedValue && (!Number.isSafeInteger(parsedSeed) || (parsedSeed ?? -1) < 0)),
    );
    if (this.filterError()) return;
    this.store.load({
      filter: this.filter.value.trim() || undefined,
      randomSeed: parsedSeed,
      skipCount: 0,
      maxResultCount: 20,
      sorting: 'createdTime desc',
    });
  }

  changePage(delta: number): void {
    this.store.changePage(delta);
  }

  metricsStatus(value: string | undefined): string {
    if (!value) return this.text.notAvailable;
    try {
      const parsed: unknown = JSON.parse(value);
      if (typeof parsed === 'object' && parsed !== null && 'status' in parsed) {
        const status = Reflect.get(parsed, 'status');
        if (status === 'NotRun') return this.text.notRun;
        if (status === 'Succeeded') return this.text.completed;
        if (status === 'Failed') return this.text.failed;
      }
      return this.text.metricsPayloadHidden;
    } catch {
      return this.text.invalidMetricsRecord;
    }
  }
}
