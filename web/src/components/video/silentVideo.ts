/**
 * The ref of every preview `<video>` in a scene card and its windows: silent from the moment it exists, before the
 * browser starts playing it. React sets `muted` as a property only after the element is made, and on some browsers an
 * autoplaying clip's sound gets out in between, again each time the card is drawn anew. `defaultMuted` also writes the
 * `muted` attribute. A player with controls keeps its volume, so a member who turns its sound on hears it; the ref runs
 * only when the element is made, so a later redraw never turns it off again.
 */
export function silentVideo(video: HTMLVideoElement | null): void {
  if (!video) return;
  video.defaultMuted = true;
  video.muted = true;
  if (!video.controls) video.volume = 0;
}
