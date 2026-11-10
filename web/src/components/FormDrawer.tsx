"use client";

import { Button, Drawer, Flex, type ButtonProps, type FormInstance } from "antd";
import { useGuardedClose } from "@/lib/unsaved";

/** A form opens in a drawer from the right, with "Huỷ" and its main button at the bottom, so the page stays in view
 * beside it and a long form scrolls inside. Takes the props a form Modal took, so the two read alike; dialogs that
 * need the full width (photo editor, stock picker, previews) and yes/no confirmations stay Modals. With `guard`, closing
 * it after typing in that form ("Huỷ", ×, a click outside, leaving the page) asks first. */
export default function FormDrawer({
  title,
  open,
  onClose,
  onOk,
  okText,
  cancelText = "Huỷ",
  confirmLoading,
  okButtonProps,
  footer,
  width = 520,
  destroyOnHidden,
  forceRender,
  afterClose,
  guard,
  children,
}: {
  title: React.ReactNode;
  open: boolean;
  onClose: () => void;
  onOk?: () => unknown;
  okText?: React.ReactNode;
  cancelText?: React.ReactNode;
  confirmLoading?: boolean;
  okButtonProps?: ButtonProps;
  /** Replaces "Huỷ" and the main button; null leaves the drawer without a footer. */
  footer?: React.ReactNode;
  width?: number;
  destroyOnHidden?: boolean;
  forceRender?: boolean;
  /** Runs once the drawer has finished closing, like Modal's afterClose. */
  afterClose?: () => void;
  /** The drawer's form, when losing its typing would cost the member: closing asks first. */
  guard?: FormInstance;
  children: React.ReactNode;
}) {
  const close = useGuardedClose(guard, open, onClose);
  return (
    <Drawer
      title={title}
      open={open}
      onClose={close}
      // Never wider than the screen: on a phone the drawer takes the whole width.
      size={`min(${width}px, 100vw)`}
      destroyOnHidden={destroyOnHidden}
      forceRender={forceRender}
      afterOpenChange={(opened) => {
        if (!opened) afterClose?.();
      }}
      footer={
        footer === undefined ? (
          <Flex justify="flex-end" gap={8}>
            <Button onClick={close}>{cancelText}</Button>
            <Button type="primary" loading={confirmLoading} onClick={() => void onOk?.()} {...okButtonProps}>
              {okText}
            </Button>
          </Flex>
        ) : (
          footer
        )
      }
    >
      {children}
    </Drawer>
  );
}
