export interface SystemStatusDto {
  service?: string;
  status?: string;
  dataset?: string;
  modality?: string;
  task?: string;
  disclaimer?: string;
  serverTimeUtc?: string;
}
