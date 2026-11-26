import { describe, expect, it, vi } from 'vitest';
import { readNiftiVolume, renderSlice, sameGrid, voxelAt, type AxialVolume } from './nifti-volume';

function createVolume(width = 2, height = 2, depth = 2): ArrayBuffer {
  const buffer = new ArrayBuffer(352 + width * height * depth * 4);
  const view = new DataView(buffer);
  view.setInt32(0, 348, true);
  view.setInt16(40, 3, true);
  view.setInt16(42, width, true);
  view.setInt16(44, height, true);
  view.setInt16(46, depth, true);
  view.setInt16(70, 16, true);
  view.setInt16(72, 32, true);
  view.setFloat32(80, 0.8, true);
  view.setFloat32(84, 0.8, true);
  view.setFloat32(88, 2.5, true);
  view.setFloat32(108, 352, true);
  view.setFloat32(112, 1, true);
  view.setInt16(254, 1, true);
  for (const [offset, value] of [
    [280, 0.8],
    [296, 0.8],
    [312, 2.5],
  ]) {
    view.setFloat32(offset, value, true);
  }
  new Uint8Array(buffer).set([110, 43, 49, 0], 344);
  for (let index = 0; index < width * height * depth; index += 1) {
    view.setFloat32(352 + index * 4, index + 1, true);
  }
  return buffer;
}

describe('NIfTI axial volume reader', () => {
  it('reads dimensions, physical metadata, and voxel order', async () => {
    const volume = await readNiftiVolume(new Blob([createVolume()]));
    expect([volume.width, volume.height, volume.depth]).toEqual([2, 2, 2]);
    expect(volume.spacing[0]).toBeCloseTo(0.8);
    expect(volume.spacing[1]).toBeCloseTo(0.8);
    expect(volume.spacing[2]).toBeCloseTo(2.5);
    expect(voxelAt(volume, 1, 0, 1)).toBe(6);
  });

  it('rejects invalid headers and mismatched grids', async () => {
    const malformed = new Uint8Array(createVolume());
    malformed[344] = 0;
    await expect(readNiftiVolume(new Blob([malformed]))).rejects.toThrow('invalidNifti');

    const first = await readNiftiVolume(new Blob([createVolume()]));
    const second = await readNiftiVolume(new Blob([createVolume(3, 2, 2)]));
    expect(sameGrid(first, second)).toBe(false);
  });

  it('renders boundary and uncertainty overlays on the source voxel grid', () => {
    const source: AxialVolume = {
      width: 2,
      height: 2,
      depth: 1,
      voxels: new Float32Array([1, 1, 1, 1]),
      spacing: [1, 1, 1],
      affine: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0],
    };
    const boundary: AxialVolume = {
      ...source,
      voxels: new Float32Array([1, 0, 0, 0]),
    };
    const uncertainty: AxialVolume = {
      ...source,
      voxels: new Float32Array([100, 100, 100, 100]),
    };
    const image = { data: new Uint8ClampedArray(16) };
    const context = {
      createImageData: vi.fn(() => image),
      putImageData: vi.fn(),
    };
    const canvas = document.createElement('canvas');
    Object.defineProperty(canvas, 'getContext', { value: () => context });

    renderSlice(canvas, source, 0, 'boundary', boundary, 1, boundary, uncertainty);
    expect([...image.data.slice(0, 3)]).toEqual([255, 176, 0]);
    renderSlice(canvas, source, 0, 'uncertainty', boundary, 1, boundary, uncertainty);
    expect([...image.data.slice(0, 3)]).toEqual([255, 0, 0]);
    expect(context.putImageData).toHaveBeenCalledTimes(2);
  });
});
