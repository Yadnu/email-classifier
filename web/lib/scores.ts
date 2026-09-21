export type BinaryScores = {
  precision: number;
  recall: number;
  f1: number;
  tp: number;
  fp: number;
  fn: number;
  tn: number;
};

export function binaryScores(yTrue: boolean[], yPred: boolean[]): BinaryScores {
  let tp = 0;
  let fp = 0;
  let fn = 0;
  let tn = 0;
  for (let i = 0; i < yTrue.length; i++) {
    const truth = yTrue[i];
    const pred = yPred[i];
    if (truth && pred) tp += 1;
    else if (pred && !truth) fp += 1;
    else if (truth && !pred) fn += 1;
    else tn += 1;
  }
  const precision = tp + fp ? tp / (tp + fp) : 0;
  const recall = tp + fn ? tp / (tp + fn) : 0;
  const f1 = precision + recall ? (2 * precision * recall) / (precision + recall) : 0;
  return { precision, recall, f1, tp, fp, fn, tn };
}
