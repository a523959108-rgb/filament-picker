/** Reorder a slot list by drag-and-drop indexes. Indexes are positions before the move. */
export function moveSlot<T>(slots: readonly T[], fromIndex: number, toIndex: number): T[] {
  if (
    fromIndex === toIndex ||
    fromIndex < 0 ||
    toIndex < 0 ||
    fromIndex >= slots.length ||
    toIndex >= slots.length
  ) {
    return [...slots];
  }
  const next = [...slots];
  const [item] = next.splice(fromIndex, 1);
  if (item === undefined) return [...slots];
  next.splice(toIndex, 0, item);
  return next;
}
