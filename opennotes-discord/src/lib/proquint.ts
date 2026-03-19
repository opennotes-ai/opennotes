const UUID_LIKE_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const PROQUINT_CONS = '[bdfghjklmnprstvz]';
const PROQUINT_VOWL = '[aiou]';
const PROQUINT_WORD = `${PROQUINT_CONS}${PROQUINT_VOWL}${PROQUINT_CONS}${PROQUINT_VOWL}${PROQUINT_CONS}`;
const PROQUINT_RE = new RegExp(`^${PROQUINT_WORD}-${PROQUINT_WORD}$`);

const PROQUINT_CONSONANTS = 'bdfghjklmnprstvz';
const PROQUINT_VOWELS = 'aiou';

function encodeProquintWord(word: number): string {
  return [
    PROQUINT_CONSONANTS[word & 0x0f],
    PROQUINT_VOWELS[(word >> 4) & 0x03],
    PROQUINT_CONSONANTS[(word >> 6) & 0x0f],
    PROQUINT_VOWELS[(word >> 10) & 0x03],
    PROQUINT_CONSONANTS[(word >> 12) & 0x0f],
  ].join('');
}

function decodeProquintWord(pq: string): number {
  let word = 0;
  word |= PROQUINT_CONSONANTS.indexOf(pq[0]);
  word |= PROQUINT_VOWELS.indexOf(pq[1]) << 4;
  word |= PROQUINT_CONSONANTS.indexOf(pq[2]) << 6;
  word |= PROQUINT_VOWELS.indexOf(pq[3]) << 10;
  word |= PROQUINT_CONSONANTS.indexOf(pq[4]) << 12;
  return word;
}

export function uuidToProquint(uuid: string): string {
  const hex = uuid.replace(/-/g, '').slice(-8).toLowerCase();
  const upperWord = Number.parseInt(hex.slice(0, 4), 16);
  const lowerWord = Number.parseInt(hex.slice(4), 16);
  return `${encodeProquintWord(upperWord)}-${encodeProquintWord(lowerWord)}`;
}

export function proquintToHexSuffix(proquint: string): string {
  const [upper, lower] = proquint.split('-');
  const upperWord = decodeProquintWord(upper);
  const lowerWord = decodeProquintWord(lower);
  return (
    upperWord.toString(16).padStart(4, '0') +
    lowerWord.toString(16).padStart(4, '0')
  );
}

export function isProquint(s: string): boolean {
  return PROQUINT_RE.test(s);
}

export function isUuidLike(id: string): boolean {
  return UUID_LIKE_RE.test(id);
}

export function formatIdDisplay(id: string): string {
  if (!isUuidLike(id)) {
    return id;
  }
  return uuidToProquint(id);
}

export function resolveId(
  input: string,
  items: Array<{ id: string }>,
): string | null {
  const byUuid = items.find((item) => item.id === input);
  if (byUuid) {
    return byUuid.id;
  }

  if (isProquint(input)) {
    const hexSuffix = proquintToHexSuffix(input);
    const byProquint = items.find((item) =>
      item.id.replace(/-/g, '').endsWith(hexSuffix),
    );
    if (byProquint) {
      return byProquint.id;
    }
  }

  return null;
}
