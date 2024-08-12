# UserCustom Shell 設定

此專案包含一系列的 Shell 腳本，用於在 Arch Linux 系統上安裝必要的軟體包並進行shell環境設定。以下是設定過程的步驟指南。

## 步驟 1: 安裝 Arch Linux 依賴

執行install_scripts裡的腳本，或請自行安裝相關軟體。

## 步驟 2: 設定 Shell 環境

安裝完必要的軟體包後，接下來您應該執行 `setup_shell` 腳本來設定您的 Shell 環境。這將包括配置 `.bashrc`、`.zshrc` 以及其他配置文件。  
附帶配置文件的軟體包含：`vim`、`alacritty`、`nnn`、`neovim`、`ohmyposh`、`tmux` 等。

## 步驟 3: 可選設置

在完成上述必要步驟後，您可以根據需要選擇執行以下腳本：


### 設定 Mamba

如果您使用 Mamba 作為 Conda 的替代品，您可以執行 `setup_mamba.sh` 腳本來設定 Mamba 環境。

```shell
./setup_mamba.sh
```
