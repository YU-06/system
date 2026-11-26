import { readNiftiVolume, type AxialVolume } from './nifti-volume';

export interface InspectedNifti {
  file: File;
  volume: AxialVolume;
  sha256: string;
}

const acceptedMimeTypes = new Set([
  '',
  'application/octet-stream',
  'application/gzip',
  'application/x-gzip',
  'application/x-nifti',
]);

export async function inspectNiftiFile(file: File): Promise<InspectedNifti> {
  const name = file.name.toLowerCase();
  if (!name.endsWith('.nii') && !name.endsWith('.nii.gz')) {
    throw new Error('invalidFileType');
  }
  if (!acceptedMimeTypes.has(file.type)) {
    throw new Error('invalidFileType');
  }
  if (file.size > 64 * 1024 * 1024) {
    throw new Error('uploadTooLarge');
  }
  if (name.endsWith('.nii') && file.size < 352) throw new Error('invalidNifti');
  const signature = new Uint8Array(await file.slice(0, 2).arrayBuffer());
  const isGzip = signature[0] === 0x1f && signature[1] === 0x8b;
  if (isGzip !== name.endsWith('.nii.gz')) throw new Error('invalidNifti');
  const [volume, bytes] = await Promise.all([readNiftiVolume(file), file.arrayBuffer()]);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const sha256 = Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
  return { file, volume, sha256 };
}
