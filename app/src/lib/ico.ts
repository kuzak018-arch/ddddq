/**
 * A Windows .ico made of PNG images (Vista and later read PNG entries of any size): the user's
 * picture for the desktop, Start menu and taskbar shortcuts, which only take an .ico file.
 */

export const ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256];

export interface IcoImage {
  size: number;
  png: Uint8Array;
}

/** ICONDIR + one ICONDIRENTRY per image, then the PNG data one after another. */
export function buildIco(images: IcoImage[]): Uint8Array {
  const head = 6 + 16 * images.length;
  const total = head + images.reduce((n, i) => n + i.png.length, 0);
  const out = new Uint8Array(total);
  const v = new DataView(out.buffer);
  v.setUint16(0, 0, true); // reserved
  v.setUint16(2, 1, true); // type: icon
  v.setUint16(4, images.length, true);
  let offset = head;
  images.forEach((img, i) => {
    const e = 6 + 16 * i;
    v.setUint8(e, img.size >= 256 ? 0 : img.size); // 0 means 256
    v.setUint8(e + 1, img.size >= 256 ? 0 : img.size);
    v.setUint8(e + 2, 0); // no palette
    v.setUint8(e + 3, 0);
    v.setUint16(e + 4, 1, true); // colour planes
    v.setUint16(e + 6, 32, true); // bits per pixel
    v.setUint32(e + 8, img.png.length, true);
    v.setUint32(e + 12, offset, true);
    out.set(img.png, offset);
    offset += img.png.length;
  });
  return out;
}

/** The sizes and offsets written in an .ico, to check one. */
export function readIco(bytes: Uint8Array): { size: number; length: number; offset: number }[] {
  const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (v.getUint16(0, true) !== 0 || v.getUint16(2, true) !== 1) throw new Error('not an icon');
  return Array.from({ length: v.getUint16(4, true) }, (_, i) => {
    const e = 6 + 16 * i;
    return { size: v.getUint8(e) || 256, length: v.getUint32(e + 8, true), offset: v.getUint32(e + 12, true) };
  });
}
