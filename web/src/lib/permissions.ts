/** The author or the owner of the destination Page may take a post down. Backend enforcement stays authoritative. */
export function canTakeDownPost(
  post: { created_by_id: number; fanpage_owner_id: number | null },
  memberId: number,
): boolean {
  return post.created_by_id === memberId || post.fanpage_owner_id === memberId;
}
