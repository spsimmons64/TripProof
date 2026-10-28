// THE hands a signature can be drawn in, offered on every signing screen, the default first. The
// key is what is stored with a signature, so it is drawn the same everywhere: the stylesheet knows
// these as .font-<key> (styles.css) and the PDF writer as SIGNATURE_FONTS (api/app/signatures.py).
// All ten are free for commercial use (SIL Open Font License, or Apache 2.0 for Satisfy) and are
// served from our own origin. Signatures already made in the earlier faces keep them.
export const SIGNATURE_FONTS = [
  { key: 'alexbrush', label: 'Alex Brush' },
  { key: 'birthstone', label: 'Birthstone' },
  { key: 'dancing', label: 'Dancing Script' },
  { key: 'ephesis', label: 'Ephesis' },
  { key: 'greatvibes', label: 'Great Vibes' },
  { key: 'kalam', label: 'Kalam' },
  { key: 'marck', label: 'Marck Script' },
  { key: 'montecarlo', label: 'Monte Carlo' },
  { key: 'satisfy', label: 'Satisfy' },
  { key: 'whisper', label: 'Whisper' },
]
// The same list as [key, label] pairs, for the screens written that way.
export const SIGNATURE_FONT_PAIRS = SIGNATURE_FONTS.map((f) => [f.key, f.label])
export const DEFAULT_FONT = SIGNATURE_FONTS[0].key
