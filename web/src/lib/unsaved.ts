"use client";

import { App } from "antd";
import type { FormInstance } from "antd";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef } from "react";

/** Asks before typing is thrown away; resolves true when the member chooses to drop it. */
export function useConfirmDiscard() {
  const { modal } = App.useApp();
  return useCallback(
    () =>
      new Promise<boolean>((resolve) => {
        modal.confirm({
          title: "Bỏ các thay đổi chưa lưu?",
          content: "Những gì bạn vừa nhập sẽ mất.",
          okText: "Bỏ thay đổi",
          okButtonProps: { danger: true },
          cancelText: "Tiếp tục sửa",
          onOk: () => resolve(true),
          onCancel: () => resolve(false),
        });
      }),
    [modal],
  );
}

/** While `dirty()` is true, leaving the page asks first: closing or reloading the tab gets the browser's own
 * question, and a link inside the app (the menu, a row) gets ours. `null` guards nothing. */
export function useLeaveGuard(dirty: (() => boolean) | null) {
  const confirm = useConfirmDiscard();
  const router = useRouter();
  const check = useRef(dirty);
  useEffect(() => {
    check.current = dirty;
  });
  const guarded = dirty !== null;
  useEffect(() => {
    if (!guarded) return;
    const isDirty = () => check.current?.() ?? false;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (isDirty()) event.preventDefault();
    };
    // Captured on the document, before Next's Link sees the click.
    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (!(link instanceof HTMLAnchorElement) || link.target === "_blank" || link.hasAttribute("download")) return;
      const url = new URL(link.href, window.location.href);
      // Another site is left through the browser, which asks by itself.
      if (url.origin !== window.location.origin) return;
      if (url.pathname === window.location.pathname && url.search === window.location.search) return;
      if (!isDirty()) return;
      event.preventDefault();
      // One question even when several parts of the page hold typing.
      event.stopImmediatePropagation();
      void confirm().then((drop) => {
        if (drop) {
          check.current = null;
          router.push(url.pathname + url.search + url.hash);
        }
      });
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    document.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
      document.removeEventListener("click", onClick, true);
    };
  }, [guarded, confirm, router]);
}

/** `onClose` for a form drawer that asks first when its fields were typed in; also guards leaving the page while it
 * is open. For a drawer with its own footer, whose "Huỷ" calls the returned function; FormDrawer's `guard` does it
 * for the rest. */
export function useGuardedClose(form: FormInstance | undefined, open: boolean, onClose: () => void) {
  const confirm = useConfirmDiscard();
  useLeaveGuard(form ? () => open && form.isFieldsTouched() : null);
  return useCallback(() => {
    if (!form?.isFieldsTouched()) return onClose();
    void confirm().then((drop) => {
      if (drop) onClose();
    });
  }, [form, confirm, onClose]);
}
