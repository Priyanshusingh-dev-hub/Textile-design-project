/** Changing colours by clicking: the engine answers a picture of the sketch's areas (each pixel's area number in
 *  its red and green bytes, 0 = a line) and what each area prints in. These are the pure parts: reading that
 *  picture, finding the area under a click, and keeping the typed list of numbers and the clicks in step. */

/** Area numbers of an RGBA pixel buffer (`ImageData.data`) made by the engine: red x 256 + green. */
export function idsFromRgba(data: ArrayLike<number>, pixels: number): Uint16Array {
  const out = new Uint16Array(pixels);
  for (let i = 0; i < pixels; i++) out[i] = data[i * 4] * 256 + data[i * 4 + 1];
  return out;
}

/** The area under a point given as fractions (0..1) of the picture's width and height; 0 on a line or outside. */
export function areaAt(ids: Uint16Array, w: number, h: number, fx: number, fy: number): number {
  if (!(fx >= 0 && fx < 1 && fy >= 0 && fy < 1)) return 0;
  return ids[Math.floor(fy * h) * w + Math.floor(fx * w)] ?? 0;
}

/** The list with `n` added, or taken out when it is there; ascending. */
export function toggleArea(list: number[], n: number): number[] {
  return list.includes(n) ? list.filter(v => v !== n) : [...list, n].sort((a, b) => a - b);
}

/** The numbers as the field shows them: "101, 104, 110-113" (runs of three or more as a range). */
export function areaList(list: number[]): string {
  const out: string[] = [];
  for (let i = 0; i < list.length;) {
    let j = i;
    while (j + 1 < list.length && list[j + 1] === list[j] + 1) j++;
    out.push(j - i >= 2 ? `${list[i]}-${list[j]}` : list.slice(i, j + 1).join(', '));
    i = j + 1;
  }
  return out.join(', ');
}

/** Pixels of `ids` that belong to `picked`, painted `rgba` into an ImageData buffer (the highlight on the picture). */
export function paintPicked(ids: Uint16Array, picked: ReadonlySet<number>, out: Uint8ClampedArray,
                            rgba: [number, number, number, number]): void {
  out.fill(0);
  if (!picked.size) return;
  for (let i = 0; i < ids.length; i++) {
    if (ids[i] && picked.has(ids[i])) {
      out[i * 4] = rgba[0]; out[i * 4 + 1] = rgba[1]; out[i * 4 + 2] = rgba[2]; out[i * 4 + 3] = rgba[3];
    }
  }
}
