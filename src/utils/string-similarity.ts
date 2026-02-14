/**
 * String Similarity Utilities
 * For fuzzy matching firm names
 */

/**
 * Calculate Levenshtein distance between two strings
 * Lower distance = more similar
 */
export function levenshteinDistance(str1: string, str2: string): number {
  const matrix: number[][] = [];

  for (let i = 0; i <= str2.length; i++) {
    matrix[i] = [i];
  }

  for (let j = 0; j <= str1.length; j++) {
    matrix[0][j] = j;
  }

  for (let i = 1; i <= str2.length; i++) {
    for (let j = 1; j <= str1.length; j++) {
      if (str2.charAt(i - 1) === str1.charAt(j - 1)) {
        matrix[i][j] = matrix[i - 1][j - 1];
      } else {
        matrix[i][j] = Math.min(
          matrix[i - 1][j - 1] + 1, // substitution
          matrix[i][j - 1] + 1, // insertion
          matrix[i - 1][j] + 1 // deletion
        );
      }
    }
  }

  return matrix[str2.length][str1.length];
}

/**
 * Calculate similarity score between 0 and 1
 * 1 = identical, 0 = completely different
 */
export function stringSimilarity(str1: string, str2: string): number {
  const s1 = str1.toLowerCase().trim();
  const s2 = str2.toLowerCase().trim();

  // Exact match
  if (s1 === s2) return 1.0;

  // Levenshtein-based similarity
  const distance = levenshteinDistance(s1, s2);
  const maxLength = Math.max(s1.length, s2.length);
  const levenshteinSimilarity = 1 - distance / maxLength;

  // Substring-based bonus
  let substringBonus = 0;
  if (s1.includes(s2) || s2.includes(s1)) {
    substringBonus = 0.1;
  }

  // Token-based matching (for handling "Ltd" vs "Limited" etc)
  const tokens1 = s1.split(/[\s\-\.]+/).filter((t) => t.length > 0);
  const tokens2 = s2.split(/[\s\-\.]+/).filter((t) => t.length > 0);

  const matchedTokens = tokens1.filter((t1) =>
    tokens2.some((t2) => {
      if (t1 === t2) return true;
      const tokenDist = levenshteinDistance(t1, t2);
      return tokenDist <= 1; // Allow 1-character difference
    })
  ).length;

  const tokenSimilarity =
    matchedTokens > 0 ? matchedTokens / Math.max(tokens1.length, tokens2.length) : 0;

  // Weighted average: 60% Levenshtein, 40% Token-based
  const finalScore = levenshteinSimilarity * 0.6 + tokenSimilarity * 0.4 + substringBonus;

  return Math.min(finalScore, 1.0);
}

/**
 * Soundex algorithm for phonetic matching
 * Useful for catching spelling variations
 */
export function soundex(str: string): string {
  const s = str.toUpperCase().replace(/[^A-Z]/g, '');
  if (s.length === 0) return '0000';

  const firstLetter = s[0];
  const codes: Record<string, string> = {
    B: '1', F: '1', P: '1', V: '1',
    C: '2', G: '2', J: '2', K: '2', Q: '2', S: '2', X: '2', Z: '2',
    D: '3', T: '3',
    L: '4',
    M: '5', N: '5',
    R: '6',
  };

  let soundexCode = firstLetter;
  let lastCode = codes[firstLetter] || '0';

  for (let i = 1; i < s.length && soundexCode.length < 4; i++) {
    const code = codes[s[i]] || '0';
    if (code !== '0' && code !== lastCode) {
      soundexCode += code;
      lastCode = code;
    } else if (code !== '0') {
      lastCode = code;
    }
  }

  // Pad with zeros
  while (soundexCode.length < 4) {
    soundexCode += '0';
  }

  return soundexCode.substring(0, 4);
}

/**
 * Phonetic similarity for name matching
 * Returns score 0-1
 */
export function phoneticSimilarity(str1: string, str2: string): number {
  const s1 = soundex(str1);
  const s2 = soundex(str2);
  return s1 === s2 ? 0.8 : 0.0; // Soundex match = 80% confidence
}

/**
 * Combined similarity score using multiple algorithms
 */
export function combinedSimilarity(str1: string, str2: string): number {
  const stringScore = stringSimilarity(str1, str2);
  const phoneticScore = phoneticSimilarity(str1, str2);

  // 70% string similarity, 30% phonetic
  return stringScore * 0.7 + phoneticScore * 0.3;
}

/**
 * Find best match from list of candidates
 */
export function findBestMatch(
  query: string,
  candidates: string[],
  threshold: number = 0.7
): { match: string; score: number } | null {
  if (candidates.length === 0) return null;

  const matches = candidates.map((candidate) => ({
    match: candidate,
    score: combinedSimilarity(query, candidate),
  }));

  const best = matches.sort((a, b) => b.score - a.score)[0];

  return best.score >= threshold ? best : null;
}
