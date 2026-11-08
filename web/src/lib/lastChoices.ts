import { api, type VideoDetail } from "./api";

/** The Page and topic group a member last picked, kept on the server by account (api routes_last_choices.py, brief
 * part B3): the create, publish and queue forms start on them, each member on their own. */
export type LastChoices = { fanpage_id: number | null; knowledge_topic_id: number | null };

const NONE: LastChoices = { fanpage_id: null, knowledge_topic_id: null };

/** Only a head start: a failure starts the form as it would without one. */
export function loadLastChoices(): Promise<LastChoices> {
  return api<LastChoices>("/me/last-choices").catch(() => NONE);
}

/** Remembers a choice once the form went through; a failure is never the member's problem. */
export function saveLastChoice(choice: Partial<LastChoices>): Promise<void> {
  return api("/me/last-choices", "PATCH", choice).then(
    () => undefined,
    () => undefined,
  );
}

/** The member's own Page that posts the video's topic group, the first one if they have several. */
export function myPageOfGroup(video: VideoDetail, meId: number | undefined): number | null {
  if (meId === undefined || video.knowledge_topic_id === null) return null;
  return (
    video.fanpages.find((page) => page.owner_id === meId && page.knowledge_topic_id === video.knowledge_topic_id)?.id ??
    null
  );
}
