import { describe, expect, it } from 'vitest';
import { inspectNiftiFile } from './nifti-file';

function createNifti(): ArrayBuffer {
  const buffer = new ArrayBuffer(368);
  const view = new DataView(buffer);
  view.setInt32(0, 348, true);
  view.setInt16(40, 3, true);
  view.setInt16(42, 2, true);
  view.setInt16(44, 2, true);
  view.setInt16(46, 1, true);
  view.setInt16(70, 16, true);
  view.setInt16(72, 32, true);
  view.setFloat32(76, 1, true);
  view.setFloat32(80, 1, true);
  view.setFloat32(84, 1, true);
  view.setFloat32(88, 1, true);
  view.setFloat32(108, 352, true);
  view.setInt16(254, 1, true);
  view.setFloat32(280, 1, true);
  view.setFloat32(300, 1, true);
  view.setFloat32(320, 1, true);
  new Uint8Array(buffer).set([110, 43, 49, 0], 344);
  for (let index = 0; index < 4; index += 1) {
    view.setFloat32(352 + index * 4, index + 1, true);
  }
  return buffer;
}

describe('complete NIfTI upload validation', () => {
  it('accepts a complete 3D NIfTI-1 file and returns its dimensions and SHA-256', async () => {
    const file = new File([createNifti()], 'study.nii', { type: 'application/octet-stream' });
    const inspected = await inspectNiftiFile(file);

    expect([inspected.volume.width, inspected.volume.height, inspected.volume.depth]).toEqual([
      2, 2, 1,
    ]);
    expect(inspected.sha256).toMatch(/^[a-f0-9]{64}$/);
  });

  it('rejects unsupported extensions and malformed image headers', async () => {
    await expect(inspectNiftiFile(new File(['x'], 'image.dcm'))).rejects.toThrow('invalidFileType');
    await expect(inspectNiftiFile(new File(['x'], 'image.nii'))).rejects.toThrow('invalidNifti');
  });
});
