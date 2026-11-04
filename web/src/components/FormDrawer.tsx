"use client";

import { Button, Drawer, Flex, type ButtonProps } from "antd";

/** A form opens in a drawer from the right, with "Huỷ" and its main button at the bottom, so the page stays in view
 * beside it and a long form scrolls inside. Takes the props a form Modal took, so the two read alike; dialogs that
 * need the full width (photo editor, stock picker, previews) and yes/no confirmations stay Modals. */
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
  children: React.ReactNode;
}) {
  return (
    <Drawer
      title={title}
      open={open}
      onClose={onClose}
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
            <Button onClick={onClose}>{cancelText}</Button>
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
