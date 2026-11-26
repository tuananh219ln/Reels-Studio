import { useStoredChoice } from "@/lib/storedChoice";

/** The rows-per-page a member can pick under every list of videos or posts. */
export const PAGE_SIZES = [5, 10, 15, 20, 50, 100] as const;

/** What a list shows before a member picks one (the owner asked for 5). */
export const DEFAULT_PAGE_SIZE = 5;

/** How many videos a page of a list shows, kept on this browser and shared by every list of videos, so a choice made
 * on one list holds on the others and after a reload. Anything stored that is not a choice reads as the default. */
export function usePageSize(): [number, (next: number) => void] {
  const [stored, store] = useStoredChoice("video-table-page-size", String(DEFAULT_PAGE_SIZE));
  const value = Number(stored);
  const size = (PAGE_SIZES as readonly number[]).includes(value) ? value : DEFAULT_PAGE_SIZE;
  return [size, (next) => store(String(next))];
}
