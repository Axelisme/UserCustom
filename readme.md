# UserCustom Shell 設定

此專案包含一系列的 Shell 腳本，用於在 Arch Linux 系統上安裝必要的軟體包並進行shell環境設定。以下是設定過程的步驟指南。

## 步驟 1: 安裝 Arch Linux 依賴

執行install_scripts裡的腳本，或請自行安裝相關軟體。  

```bash
# install all in system
./install_scripts/system/install_all.sh

# install all in user home
./install_scripts/install_all.sh

# install respectively in user home
./install_scripts/install_{xxx}.sh
```

## 步驟 2: 設定 Shell 環境

安裝完必要的軟體包後，接下來您應該執行 `setup_shell` 腳本來設定您的 Shell 環境。這將包括配置 `.bashrc`、`.zshrc`  
以及執行`setup_config.sh`來設定其他配置文件。  
附帶配置文件的軟體包含：`vim`、`alacritty`、`nnn`、`neovim`、`ohmyposh`、`tmux` 等。

```bash
# setup .bashrc, .zshrc, and others
./setup_scripts/setup_shell.sh
./setup_scripts/setup_config.sh
```

## 步驟 3: 設定其他軟體(Optional)

```bash
./setup_scripts/setup_mamba.sh
./setup_scripts/setup_git.sh
./setup_scripts/setup_yazi.sh
./setup_scripts/setup_rime-frost.sh
```
