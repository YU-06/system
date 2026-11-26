import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { I18nService } from '../localization/i18n.service';

@Component({
  selector: 'app-access-denied',
  imports: [RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="feature-page" aria-labelledby="access-denied-title">
      <div class="panel">
        <p class="eyebrow">{{ text.accessDeniedEyebrow }}</p>
        <h1 id="access-denied-title">{{ text.accessDeniedTitle }}</h1>
        <p class="muted">{{ text.accessDeniedMessage }}</p>
        <a class="primary-button link-button" routerLink="/">{{ text.overview }}</a>
      </div>
    </section>
  `,
})
export class AccessDeniedComponent {
  readonly text = inject(I18nService).text;
}
