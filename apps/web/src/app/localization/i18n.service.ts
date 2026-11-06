import { Injectable } from '@angular/core';
import resource from './zh-Hans.json';

@Injectable({ providedIn: 'root' })
export class I18nService {
  readonly text = resource;
}
