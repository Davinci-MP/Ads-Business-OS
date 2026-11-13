// Client-side RFC 6238 TOTP computation using Web Crypto API

export function base32ToBytes(base32: string): Uint8Array {
  const clean = base32.replace(/[\s=-]/g, "").toUpperCase();
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = 0;
  let value = 0;
  const output: number[] = [];
  for (let i = 0; i < clean.length; i++) {
    const idx = alphabet.indexOf(clean[i]);
    if (idx === -1) continue;
    value = (value << 5) | idx;
    bits += 5;
    if (bits >= 8) {
      output.push((value >>> (bits - 8)) & 255);
      bits -= 8;
    }
  }
  return new Uint8Array(output);
}

export async function computeClientTotp(secret: string): Promise<{ code: string; remaining: number } | null> {
  if (!secret) return null;
  const cleanSecret = secret.replace(/\s+/g, "").trim();
  if (cleanSecret.length < 8) return null;

  try {
    const keyBytes = base32ToBytes(cleanSecret);
    if (keyBytes.length === 0) return null;
    const epoch = Math.floor(Date.now() / 1000);
    const timeStep = 30;
    const counter = Math.floor(epoch / timeStep);
    const remaining = timeStep - (epoch % timeStep);

    const buffer = new ArrayBuffer(8);
    const view = new DataView(buffer);
    view.setUint32(0, 0, false);
    view.setUint32(4, counter, false);

    if (typeof window !== "undefined" && window.crypto && window.crypto.subtle) {
      const cryptoKey = await window.crypto.subtle.importKey(
        "raw",
        keyBytes as unknown as BufferSource,
        { name: "HMAC", hash: "SHA-1" },
        false,
        ["sign"]
      );
      const signature = await window.crypto.subtle.sign("HMAC", cryptoKey, buffer);
      const sigBytes = new Uint8Array(signature);
      const offset = sigBytes[sigBytes.length - 1] & 0x0f;
      const binary =
        ((sigBytes[offset] & 0x7f) << 24) |
        ((sigBytes[offset + 1] & 0xff) << 16) |
        ((sigBytes[offset + 2] & 0xff) << 8) |
        (sigBytes[offset + 3] & 0xff);
      const otp = (binary % 1000000).toString().padStart(6, "0");
      return { code: otp, remaining };
    }
    return null;
  } catch {
    return null;
  }
}
