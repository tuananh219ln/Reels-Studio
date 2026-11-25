/**
 * iOS Safari lets a page speak only when its first sentence is started inside a tap, and "Xem trước" reads each
 * scene a moment after the tap that opened or played it. A silent sentence spoken by that tap lets the later ones
 * through; other browsers just say nothing for it.
 */
export function unlockSpeech() {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) {
    return;
  }
  const silent = new SpeechSynthesisUtterance(" ");
  silent.volume = 0;
  window.speechSynthesis.speak(silent);
}

/**
 * Stops what the browser is reading, only when it is reading: Safari can drop the next sentence when `cancel` comes
 * right before it with nothing to stop.
 */
export function stopSpeech() {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) {
    return;
  }
  if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
    window.speechSynthesis.cancel();
  }
}
