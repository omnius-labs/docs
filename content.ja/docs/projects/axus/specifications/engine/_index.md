---
title: "Engine"
weight: 1
---
- Fileについて
    - FileRef
        - Fileを検索するための情報をFileRefと呼ぶ。
        - FileRefは以下の情報を持つ。
            - MerkleTreeのルートのハッシュ値。
    - Fileデータ
        - FileはBlobStorageにブロック毎にコピーされる。
        - 分割後のブロックのサイズは256KB ~ 64MBの間。
        - ユーザーがUploadしたFileと、システムが内部でUploadしたファイルと区別できるようにする。
            - たとえば、掲示板機能を提供する場合、Fileとして掲示板情報を格納し、MemoにはFileのリンク情報を格納する。これらはシステム内部の処理として隠蔽する。
- Memoについて
    - MemoRef
        - Memoを検索するための情報をMemoRefと呼ぶ。
        - MemoRefは以下の情報を持つ。
            - 証明書
    - Memoデータ
        - サイズは最大8MBとする。
        - データの分割は無し。
            - MerkleTreeも存在しない。
