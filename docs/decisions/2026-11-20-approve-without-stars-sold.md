# 2026-11-20: A product can be approved without its stars and sales filled in

Narrows "A product becomes approved only with ... at least 4.7 stars, at least 100 sales" of
[decisions.md](../decisions.md) (2026-10-31) (the owner's request, 2026-11-20: "duyệt mà không cần nhập loại, sao, bán").

## Context

Products from the Shopee file or pasted links arrive with stars 0 and sales 0, so "Duyệt" stayed disabled until
each row was filled in by hand ("Sửa nhanh"), which is slow for a batch of 50.

## Decision

- Stars or sales of 0 mean "not filled in" and no longer block approval. A figure that is filled in and under the
  bar (below 4.7 stars, below 100 sales) still blocks, as do the banned words, the expired commission and the
  TikTok Shop rules. Shop type never mattered for Shopee since 2026-11-05.
- The tab "Cần điền sao, lượt bán" and "Sửa nhanh" stay, to fill the figures in when a member wants to.
