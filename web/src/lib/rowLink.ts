import type { MouseEvent } from "react";

/** The click handlers of a row or card that opens `href` without being a link itself: a plain click goes there in
 * the app, Ctrl/Cmd/Shift-click and the middle button open a new tab, like a real link. A click on a link or button
 * inside it keeps its own. Right-click "Mở trong tab mới" needs a real `<a>`, so the row's title is one too. */
export function rowLink(push: (href: string) => void, href: string) {
  const inside = (event: MouseEvent) => Boolean((event.target as HTMLElement).closest("a, button, input, .ant-select"));
  return {
    onClick: (event: MouseEvent) => {
      if (inside(event)) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey) window.open(href, "_blank");
      else push(href);
    },
    onAuxClick: (event: MouseEvent) => {
      if (event.button === 1 && !inside(event)) window.open(href, "_blank");
    },
  };
}
