---
title: "使い方"
weight: 1
---

## 環境構築

### Windowsの場合

Lxnaはffmpegを用いて動画のサムネイルを生成します。
そのため、事前にffmpegをインストールする必要があります。

#### 1. scoopをインストールする

scoopが未インストールの場合、下記コマンドをPowerShellで実行し、scoopをインストールします。

{{< highlight powershell "linenos=inline, linenostart=1" >}}
iwr -useb get.scoop.sh | iex
{{< /highlight >}}

参考: https://github.com/lukesampson/scoop

#### 2. ffmpegをインストールする

下記コマンドをPowerShellで実行し、ffmpegをインストールします。

{{< highlight powershell "linenos=inline, linenostart=1" >}}
scoop install ffmpeg
{{< /highlight >}}
