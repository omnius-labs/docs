---
title: "Memo"
weight: 1
---

# Memos

## 2024-05-26

- memo情報の検索について
  - memo自体に署名された情報をもとに、AssetKeyを生成して、それを検索する
    - memoに特定のタグ情報を載せて、それをもとにAssetKeyを生成して検索する方法も考えたが、結局は、WoTに基づいて、署名でフィルタリングを行うため、署名情報をもとにAssetKeyを生成する方法でカバーできると考えた
    - 荒らし対策としても、署名を用いた検索の方が有用