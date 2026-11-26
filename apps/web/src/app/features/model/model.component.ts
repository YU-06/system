import { AsyncPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { ModelArchitecture, type ModelVersionDto } from '../../proxy/research';
import { modelArchitectureOptions } from '../../proxy/research/model-architecture.enum';
import { I18nService } from '../../localization/i18n.service';
import { ResearchAccessService } from '../../shared/research-access.service';
import { ModelStore } from './model.store';

@Component({
  selector: 'app-model-library',
  imports: [AsyncPipe, ReactiveFormsModule],
  providers: [ModelStore],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './model.component.html',
})
export class ModelComponent {
  readonly text = inject(I18nService).text;
  readonly store = inject(ModelStore);
  readonly access = inject(ResearchAccessService);
  readonly canManage$ = this.access.can$('BrainSeg.ModelVersions.Manage');
  readonly architectures = modelArchitectureOptions;
  readonly filter = new FormControl('', { nonNullable: true });
  readonly architecture = new FormControl('', { nonNullable: true });

  constructor() {
    this.store.load();
  }

  load(): void {
    const selected = Object.values(ModelArchitecture).find(
      (value) => value === this.architecture.value,
    );
    this.store.load({
      filter: this.filter.value.trim() || undefined,
      architecture: selected,
      skipCount: 0,
      maxResultCount: 20,
      sorting: 'creationTime desc',
    });
  }

  changePage(delta: number): void {
    this.store.changePage(delta);
  }

  architectureLabel(value: ModelVersionDto['architecture']): string {
    return value === ModelArchitecture.AttentionUNet
      ? this.text.attentionUNet
      : value === ModelArchitecture.UNet
        ? this.text.unet
        : this.text.notAvailable;
  }
}
