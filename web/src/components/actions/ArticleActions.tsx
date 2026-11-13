"use client";
import { useMe } from "@/components/MeContext";
import { MakeReelButton, PublishButton } from "@/components/article/ArticlePosting";
import { api, errorMessage, type Article } from "@/lib/api";
import { App, Button, Flex, Popconfirm } from "antd";

export function DeleteArticleButton({
  article,
  onDeleted,
}: {
  article: Article;
  onDeleted: () => void | Promise<void>;
}) {
  const { me } = useMe();
  const { message } = App.useApp();
  if (article.created_by_id !== me.id) return null;
  return (
    <Popconfirm
      title="Xoá bài viết này?"
      okText="Xoá"
      cancelText="Không"
      okButtonProps={{ danger: true }}
      onConfirm={async () => {
        try {
          await api(`/articles/${article.id}`, "DELETE");
          await onDeleted();
        } catch (err) {
          message.error(errorMessage(err));
        }
      }}
    >
      <Button danger disabled={article.busy} aria-label="Xoá bài viết">
        Xoá
      </Button>
    </Popconfirm>
  );
}

export default function ArticleActions({
  article,
  onChanged,
}: {
  article: Article;
  onChanged: () => void | Promise<void>;
}) {
  return (
    <Flex gap={4} wrap onClick={(event) => event.stopPropagation()}>
      <PublishButton
        article={article}
        options={null}
        disabled={article.busy}
        onSaved={() => void onChanged()}
        beforePublish={async () => {}}
      />
      <MakeReelButton article={article} />
      <DeleteArticleButton article={article} onDeleted={onChanged} />
    </Flex>
  );
}
