import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { NgIcon, provideIcons } from '@ng-icons/core';
import {
  lucideActivity,
  lucideCircleCheck,
  lucideCircleX,
  lucideFileClock,
  lucideFlaskConical,
  lucideRefreshCw,
} from '@ng-icons/lucide';
import { I18nService } from '../../localization/i18n.service';
import { SystemStatusStore } from './system-status.store';

@Component({
  selector: 'app-system',
  imports: [DatePipe, NgIcon],
  providers: [
    provideIcons({
      lucideActivity,
      lucideCircleCheck,
      lucideCircleX,
      lucideFileClock,
      lucideFlaskConical,
      lucideRefreshCw,
    }),
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './system.component.html',
})
export class SystemComponent {
  readonly text = inject(I18nService).text;
  readonly store = inject(SystemStatusStore);
  readonly connected = computed(() => this.store.state().kind === 'success');
  readonly loading = computed(() => this.store.state().kind === 'loading');
}
