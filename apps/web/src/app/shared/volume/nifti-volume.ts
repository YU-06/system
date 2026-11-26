export interface AxialVolume {
  width: number;
  height: number;
  depth: number;
  voxels: Float32Array;
  spacing: readonly [number, number, number];
  affine: readonly number[];
}

const maximumCompressedBytes = 64 * 1024 * 1024;
const maximumExpandedBytes = 128 * 1024 * 1024;
const maximumVoxels = 16_777_216;

export async function readNiftiVolume(blob: Blob): Promise<AxialVolume> {
  if (blob.size > maximumCompressedBytes) {
    throw new Error('uploadTooLarge');
  }

  const input = await blob.arrayBuffer();
  const bytes = new Uint8Array(input);
  const expanded = bytes[0] === 0x1f && bytes[1] === 0x8b ? await gunzip(input) : input;
  if (expanded.byteLength > maximumExpandedBytes) {
    throw new Error('expandedTooLarge');
  }
  return parseNifti1(expanded);
}

function parseNifti1(buffer: ArrayBuffer): AxialVolume {
  if (buffer.byteLength < 352) {
    throw new Error('invalidNifti');
  }

  const view = new DataView(buffer);
  const littleEndian =
    view.getInt32(0, true) === 348 ? true : view.getInt32(0, false) === 348 ? false : null;
  if (
    littleEndian === null ||
    new TextDecoder().decode(new Uint8Array(buffer, 344, 4)) !== 'n+1\u0000'
  ) {
    throw new Error('invalidNifti');
  }
  if (view.getInt16(40, littleEndian) !== 3) {
    throw new Error('invalidDimensions');
  }

  const width = view.getInt16(42, littleEndian);
  const height = view.getInt16(44, littleEndian);
  const depth = view.getInt16(46, littleEndian);
  const voxelCount = width * height * depth;
  if (
    width < 1 ||
    width > 512 ||
    height < 1 ||
    height > 512 ||
    depth < 1 ||
    depth > 512 ||
    voxelCount > maximumVoxels
  ) {
    throw new Error('invalidDimensions');
  }

  const datatype = view.getInt16(70, littleEndian);
  const bitpix = view.getInt16(72, littleEndian);
  const bytesPerVoxel = datatypeBytes(datatype);
  if (bytesPerVoxel * 8 !== bitpix) {
    throw new Error('invalidDatatype');
  }
  const offset = view.getFloat32(108, littleEndian);
  const end = offset + voxelCount * bytesPerVoxel;
  if (!Number.isSafeInteger(offset) || offset < 352 || end > buffer.byteLength) {
    throw new Error('invalidNifti');
  }

  const rawSlope = view.getFloat32(112, littleEndian);
  const slope = Number.isFinite(rawSlope) && rawSlope !== 0 ? rawSlope : 1;
  const rawIntercept = view.getFloat32(116, littleEndian);
  const intercept = Number.isFinite(rawIntercept) ? rawIntercept : 0;
  const voxels = new Float32Array(voxelCount);
  for (let index = 0; index < voxelCount; index += 1) {
    const value = readValue(view, offset + index * bytesPerVoxel, datatype, littleEndian);
    const scaled = value * slope + intercept;
    if (!Number.isFinite(scaled)) {
      throw new Error('invalidVoxelValues');
    }
    voxels[index] = scaled;
  }

  const spacing = [1, 2, 3].map((axis) => {
    const value = Math.abs(view.getFloat32(76 + axis * 4, littleEndian));
    if (!Number.isFinite(value) || value <= 0) throw new Error('invalidSpatialMetadata');
    return value;
  }) as [number, number, number];

  const affine =
    view.getInt16(254, littleEndian) > 0
      ? [280, 296, 312].flatMap((rowOffset) =>
          [0, 4, 8, 12].map((columnOffset) =>
            view.getFloat32(rowOffset + columnOffset, littleEndian),
          ),
        )
      : view.getInt16(252, littleEndian) > 0
        ? qformAffine(view, littleEndian, spacing)
        : [spacing[0], 0, 0, 0, 0, spacing[1], 0, 0, 0, 0, spacing[2], 0];
  if (affine.some((value) => !Number.isFinite(value))) {
    throw new Error('invalidSpatialMetadata');
  }

  return { width, height, depth, voxels, spacing, affine };
}

function qformAffine(
  view: DataView,
  littleEndian: boolean,
  spacing: readonly [number, number, number],
): number[] {
  const b = view.getFloat32(256, littleEndian);
  const c = view.getFloat32(260, littleEndian);
  const d = view.getFloat32(264, littleEndian);
  const norm = b * b + c * c + d * d;
  const a = norm <= 1 ? Math.sqrt(1 - norm) : 0;
  const qfac = view.getFloat32(76, littleEndian) < 0 ? -1 : 1;
  const [dx, dy, dz] = spacing;
  const rotation = [
    a * a + b * b - c * c - d * d,
    2 * (b * c - a * d),
    2 * (b * d + a * c),
    2 * (b * c + a * d),
    a * a + c * c - b * b - d * d,
    2 * (c * d - a * b),
    2 * (b * d - a * c),
    2 * (c * d + a * b),
    a * a + d * d - c * c - b * b,
  ];
  return [
    rotation[0] * dx,
    rotation[1] * dy,
    rotation[2] * dz * qfac,
    view.getFloat32(268, littleEndian),
    rotation[3] * dx,
    rotation[4] * dy,
    rotation[5] * dz * qfac,
    view.getFloat32(272, littleEndian),
    rotation[6] * dx,
    rotation[7] * dy,
    rotation[8] * dz * qfac,
    view.getFloat32(276, littleEndian),
  ];
}

function datatypeBytes(datatype: number): number {
  switch (datatype) {
    case 2:
    case 256:
      return 1;
    case 4:
    case 512:
      return 2;
    case 8:
    case 16:
    case 768:
      return 4;
    case 64:
      return 8;
    default:
      throw new Error('invalidDatatype');
  }
}

function readValue(
  view: DataView,
  offset: number,
  datatype: number,
  littleEndian: boolean,
): number {
  switch (datatype) {
    case 2:
      return view.getUint8(offset);
    case 4:
      return view.getInt16(offset, littleEndian);
    case 8:
      return view.getInt32(offset, littleEndian);
    case 16:
      return view.getFloat32(offset, littleEndian);
    case 64:
      return view.getFloat64(offset, littleEndian);
    case 256:
      return view.getInt8(offset);
    case 512:
      return view.getUint16(offset, littleEndian);
    case 768:
      return view.getUint32(offset, littleEndian);
    default:
      throw new Error('invalidDatatype');
  }
}

async function gunzip(buffer: ArrayBuffer): Promise<ArrayBuffer> {
  if (typeof DecompressionStream === 'undefined') {
    throw new Error('gzipUnsupported');
  }

  const stream = new Blob([buffer]).stream().pipeThrough(new DecompressionStream('gzip'));
  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > maximumExpandedBytes) {
        await reader.cancel();
        throw new Error('expandedTooLarge');
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }

  const output = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return output.buffer;
}

export function voxelAt(volume: AxialVolume, x: number, y: number, slice: number): number {
  return volume.voxels[slice * volume.width * volume.height + y * volume.width + x] ?? 0;
}

export function renderSlice(
  canvas: HTMLCanvasElement,
  source: AxialVolume,
  slice: number,
  mode: 'source' | 'mask' | 'overlay' | 'contour',
  mask: AxialVolume | undefined,
  opacity: number,
): void {
  if (slice < 0 || slice >= source.depth || (mask && !sameGrid(source, mask))) {
    throw new Error('sliceUnavailable');
  }
  canvas.width = source.width;
  canvas.height = source.height;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('canvasUnavailable');
  const image = context.createImageData(source.width, source.height);
  const { minimum, maximum } = intensityRange(source);

  for (let y = 0; y < source.height; y += 1) {
    for (let x = 0; x < source.width; x += 1) {
      const index = y * source.width + x;
      const intensity = voxelAt(source, x, y, slice);
      const gray =
        intensity === 0 ? 0 : Math.round(((intensity - minimum) / (maximum - minimum)) * 255);
      const foreground = mask ? voxelAt(mask, x, y, slice) > 0 : false;
      let red = mode === 'mask' ? (foreground ? 255 : 0) : gray;
      let green = mode === 'mask' ? (foreground ? 255 : 0) : gray;
      let blue = mode === 'mask' ? (foreground ? 255 : 0) : gray;

      if (mode === 'overlay' && foreground) {
        red = Math.round(gray * (1 - opacity) + 225 * opacity);
        green = Math.round(gray * (1 - opacity) + 72 * opacity);
        blue = Math.round(gray * (1 - opacity) + 72 * opacity);
      } else if (mode === 'contour' && foreground && isContour(mask, x, y, slice)) {
        red = 255;
        green = 204;
        blue = 64;
      } else if (mode === 'contour' || mode === 'overlay') {
        red = gray;
        green = gray;
        blue = gray;
      }

      const pixel = index * 4;
      image.data[pixel] = red;
      image.data[pixel + 1] = green;
      image.data[pixel + 2] = blue;
      image.data[pixel + 3] = 255;
    }
  }
  context.putImageData(image, 0, 0);
}

export function sameGrid(first: AxialVolume, second: AxialVolume): boolean {
  return (
    first.width === second.width &&
    first.height === second.height &&
    first.depth === second.depth &&
    first.affine.every(
      (value, index) => Math.abs(value - (second.affine[index] ?? Number.NaN)) < 1e-4,
    )
  );
}

function isContour(mask: AxialVolume | undefined, x: number, y: number, slice: number): boolean {
  if (!mask || x === 0 || y === 0 || x === mask.width - 1 || y === mask.height - 1) return true;
  return (
    voxelAt(mask, x - 1, y, slice) === 0 ||
    voxelAt(mask, x + 1, y, slice) === 0 ||
    voxelAt(mask, x, y - 1, slice) === 0 ||
    voxelAt(mask, x, y + 1, slice) === 0
  );
}

function intensityRange(volume: AxialVolume): { minimum: number; maximum: number } {
  let minimum = Number.POSITIVE_INFINITY;
  let maximum = Number.NEGATIVE_INFINITY;
  for (const value of volume.voxels) {
    if (value !== 0) {
      minimum = Math.min(minimum, value);
      maximum = Math.max(maximum, value);
    }
  }
  if (!Number.isFinite(minimum) || maximum <= minimum) return { minimum: 0, maximum: 1 };
  return { minimum, maximum };
}
